# -*- coding: utf-8 -*-
"""prob01 计算入口：读取附件 1，求解计划购电 LP，写出 result1.xlsx 与全部追踪产物。

用法（正式任务，由 computation 阶段的 resource-manager 通过 tasks.py 提交）::

    <venv>/python run_prob01.py --data data/附件1.xlsx --template data/附件5/result1.xlsx \\
        --output problems/microgrid_2025/prob01/versions/assumption_v003/results/<run> \\
        --periods 144 --time-limit 60

探针模式（``--periods`` 小于 144）只用于接口自检：不写 ``result1.xlsx``，改写
``probe_result1.xlsx``，并跳过解析界与量级检查。完整计算必须由 Runner/tasks.py 创建隔离 task 执行。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from prob01_io import (
    Attachment1,
    InputValidationError,
    fill_result_workbook,
    inspect_template,
    read_attachment1,
    write_json,
)
from prob01_model import (
    C_CAP,
    DELTA_T,
    E_INIT,
    ETA_CH,
    ETA_DIS,
    ETA_ROUND_TRIP,
    P_MAX,
    Q_CAP,
    LpData,
    evaluate,
    solve_lp,
)

PROJECT_MARKERS = ("pyproject.toml", "AGENTS.md")
TABLE1_SLOTS: tuple[tuple[str, int], ...] = (
    ("10:00-10:10", 60),
    ("12:00-12:10", 72),
    ("14:00-14:10", 84),
    ("16:00-16:10", 96),
    ("18:00-18:10", 108),
    ("20:00-20:10", 120),
)
EXIT_OK = 0
EXIT_SOLVER_NOT_OPTIMAL = 2
EXIT_INPUT_INVALID = 3
EXIT_HARD_CHECK_FAILED = 4


def project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current, *current.parents):
        if all((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    raise RuntimeError("无法从脚本位置定位项目根目录")


def resolve(path_text: str) -> Path:
    candidate = Path(path_text)
    return candidate if candidate.is_absolute() else (project_root() / candidate)


def code_fingerprint(code_dir: Path) -> dict[str, str]:
    digest = hashlib.sha256()
    files: dict[str, str] = {}
    for path in sorted(code_dir.glob("*.py")):
        payload = path.read_bytes()
        files[path.name] = hashlib.sha256(payload).hexdigest()
        digest.update(path.name.encode("utf-8"))
        digest.update(payload)
    files["__code_dir__"] = digest.hexdigest()
    return files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="prob01 计划购电 LP 求解器（assumption_v003 / formulation_v001）")
    parser.add_argument("--data", default="data/附件1.xlsx", help="附件 1 路径（只读）")
    parser.add_argument("--template", default="data/附件5/result1.xlsx", help="result1.xlsx 模板路径（只读）")
    parser.add_argument("--output", required=True, help="输出目录（必须在 assumption_v003 版本目录内）")
    parser.add_argument("--periods", type=int, default=144, help="时段数；<144 为探针模式")
    parser.add_argument("--time-limit", type=float, default=60.0, help="HiGHS 求解时限（秒）")
    return parser.parse_args(argv)


def build_tables(
    metrics: dict[str, Any],
    attachment: Attachment1,
    template_info: dict[str, Any],
    periods: int,
    probe_mode: bool,
) -> dict[str, Any]:
    """构造表 1/表 2 的行映射，并按 AS01 校验位置口径。

    AS01 的位置口径要求**两个**标签同时在位：
      * 附件 1 第 i 行时间戳 = 区间左端点（如 ``10:00``）；
      * ``result1.xlsx`` 第 i 行标签 = 完整区间（如 ``10:00-10:10``）。
    只比对其中一个都会把「时间戳 vs 区间标签」的语义混淆（v1 实现的缺陷）。
    """
    labels = attachment.time_labels
    plan_labels = template_info["plan_labels"]
    purchase = metrics["series"]["purchase_kwh"]
    rows: list[dict[str, Any]] = []
    for name, position in TABLE1_SLOTS:
        if position <= periods:
            attachment_label = labels[position - 1] if position <= len(labels) else None
            template_label = plan_labels[position - 1] if position <= len(plan_labels) else None
            slot_start = name.split("-")[0]
            rows.append(
                {
                    "slot": name,
                    "position": position,
                    "attachment_timestamp": attachment_label,
                    "template_label": template_label,
                    "label_matches": attachment_label == slot_start and template_label == name,
                    "purchase_kwh": round(float(purchase[position - 1]), 6),
                }
            )
    return {
        "table1": {
            "slots": rows,
            "all_day_energy_kwh": metrics["total_purchase_kwh"],
            "all_day_cost_yuan": metrics["objective_yuan"],
        },
        "table2": {
            "block_charge_kwh": metrics["block_charge_kwh"],
            "block_discharge_kwh": metrics["block_discharge_kwh"],
            "storage_0_00_kwh": E_INIT,
            "storage_24_00_kwh": metrics["storage_final_kwh"],
            "clock_semantics": not probe_mode,
            "note": "0:00/24:00 为计划窗首/末状态（AS01 左端点口径）；探针模式下仅为截断窗端点",
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_path = resolve(args.data)
    template_path = resolve(args.template)
    output_dir = resolve(args.output)
    code_dir = Path(__file__).resolve().parent
    probe_mode = args.periods < 144

    if not 2 <= args.periods <= 144:
        print(f"[prob01] --periods 必须在 [2, 144]，收到 {args.periods}", file=sys.stderr)
        return EXIT_INPUT_INVALID
    try:
        template_info = inspect_template(template_path)
        attachment = read_attachment1(data_path, expected_rows=144)
    except InputValidationError as exc:
        print(f"[prob01] 输入校验失败：{exc}", file=sys.stderr)
        return EXIT_INPUT_INVALID

    periods = args.periods
    lp_data = LpData(
        price=attachment.price[:periods].copy(),
        load_kw=attachment.load_kw[:periods].copy(),
        pv_kw=attachment.pv_kw[:periods].copy(),
        periods=periods,
        time_labels=tuple(attachment.time_labels[:periods]),
    )
    solution = solve_lp(lp_data, time_limit_seconds=args.time_limit)
    run_meta = {
        "problem_id": "microgrid_2025",
        "question_id": "prob01",
        "assumption_version": "assumption_v003",
        "formulation_version": "formulation_v001",
        "stage": "computation",
        "probe_mode": probe_mode,
        "periods": periods,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_id": os.environ.get("AUTOMM_TASK_ID"),
        "output_directory": str(output_dir),
        "device": "cpu",
        "gpu_required": False,
        "seed": None,
        "deterministic": True,
        "solver": "scipy.optimize.linprog(method='highs')",
        "time_limit_seconds": args.time_limit,
        "input": {
            "attachment1": str(data_path),
            "attachment1_md5": attachment.md5,
            "attachment1_rows": attachment.periods,
            "template": str(template_path),
            "template_plan_periods": template_info["plan_periods"],
        },
        "parameters": {
            "delta_t_h": DELTA_T,
            "eta_ch": ETA_CH,
            "eta_dis": ETA_DIS,
            "eta_round_trip": ETA_ROUND_TRIP,
            "e_init_kwh": E_INIT,
            "p_max_kw": P_MAX,
            "c_cap_kwh": C_CAP,
            "q_dis_cap_kwh": Q_CAP,
        },
        "code_sha256": code_fingerprint(code_dir),
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
    }

    if solution.status != 0:
        status_payload = {
            "status": solution.status,
            "message": solution.message,
            "feasible_incumbent": False,
            "objective_yuan": None,
            "iterations": solution.iterations,
        }
        write_json(output_dir / "solver_status.json", status_payload)
        write_json(output_dir / "run_manifest.json", {**run_meta, "outcome": "solver_not_optimal"})
        print(f"[prob01] 求解未达最优：status={solution.status} {solution.message}", file=sys.stderr)
        return EXIT_SOLVER_NOT_OPTIMAL

    metrics = evaluate(solution, full_horizon=not probe_mode)
    tables = build_tables(metrics, attachment, template_info, periods, probe_mode)
    label_checks = [item["label_matches"] for item in tables["table1"]["slots"]]
    if not all(label_checks):
        bad = [item for item in tables["table1"]["slots"] if not item["label_matches"]]
        print(f"[prob01] 模板/附件时段标签与 AS01 位置口径不一致：{bad}", file=sys.stderr)
        return EXIT_HARD_CHECK_FAILED

    workbook_name = "probe_result1.xlsx" if probe_mode else "result1.xlsx"
    workbook_info = fill_result_workbook(
        template=template_path,
        dest=output_dir / workbook_name,
        purchase_kwh=metrics["series"]["purchase_kwh"],
        charge_kwh=metrics["series"]["charge_kwh"],
        discharge_kwh=metrics["series"]["discharge_kwh"],
        e_init=E_INIT,
        e_final=metrics["storage_final_kwh"],
        periods=periods,
    )

    failed = list(metrics["checks_failed"])
    hard_failed = list(failed)
    write_json(output_dir / "solver_status.json", {
        "status": solution.status,
        "message": solution.message,
        "solver": "highs",
        "iterations": solution.iterations,
        "objective_yuan": metrics["objective_yuan"],
        "feasible_incumbent": True,
        "mip_gap": None,
        "device": "cpu",
        "gpu_required": False,
        "seed": None,
        "equality_residual_max": solution.equality_residual_max,
        "bound_violation_max": solution.bound_violation_max,
        "deterministic": True,
    })
    write_json(output_dir / "solution.json", {
        "objective_yuan": metrics["objective_yuan"],
        "totals": {key: metrics[key] for key in (
            "total_purchase_kwh",
            "total_charge_kwh",
            "total_discharge_kwh",
            "total_spill_kwh",
            "net_load_kwh",
            "max_charge_kwh",
            "max_discharge_kwh",
            "max_side_power_kw",
            "storage_initial_kwh",
            "storage_final_kwh",
        )},
        "storage_range_kwh": metrics["storage_range_kwh"],
        "simultaneous_charge_discharge_periods": metrics["simultaneous_charge_discharge_periods"],
        "identities": {
            "I1_residual": metrics["identity_I1_residual"],
            "I2_residual": metrics["identity_I2_residual"],
        },
        "checks": metrics["checks"],
        "checks_failed": failed,
        "series": metrics["series"],
    })
    write_json(output_dir / "tables.json", tables)
    write_json(output_dir / "run_manifest.json", {
        **run_meta,
        "outcome": "hard_check_failed" if hard_failed else "completed",
        "workbook": workbook_name,
        "workbook_info": workbook_info,
        "checks_failed": failed,
        "objective_yuan": metrics["objective_yuan"],
        "total_purchase_kwh": metrics["total_purchase_kwh"],
        "total_spill_kwh": metrics["total_spill_kwh"],
    })

    print(
        f"[prob01] {'探针' if probe_mode else '正式'}运行完成：periods={periods} "
        f"C*={metrics['objective_yuan']:.4f} 元，sum_b={metrics['total_purchase_kwh']:.4f} kWh，"
        f"sum_spill={metrics['total_spill_kwh']:.4f} kWh，失败检查={failed}"
    )
    if hard_failed:
        print(f"[prob01] 硬检查未通过：{hard_failed}", file=sys.stderr)
        return EXIT_HARD_CHECK_FAILED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
