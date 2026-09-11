# -*- coding: utf-8 -*-
"""prob02 计算入口：读取附件 1/2，求解 M1 长时域 LP，写出 ``result2.xlsx`` 与全部追踪产物。

用法（正式任务，由 computation 阶段的 resource-manager 通过 ``scripts/compute_dispatcher.py`` 提交）::

    <venv>/python run_prob02.py --data data/附件1.xlsx --data2 data/附件2.xlsx \\
        --template data/附件5/result2.xlsx \\
        --output problems/microgrid_2025/prob02/versions/assumption_v001/results/<run> \\
        --days 365 --time-limit 300

探针模式（``--days`` 小于 365）只用于接口自检：不写 ``result2.xlsx``，改写 ``probe_result2.xlsx``，
并跳过解析界与量级检查。完整计算必须由 Runner/tasks.py 创建隔离 task（supervised worker）执行。
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
from prob02_io import (
    PLAN_SHEET,
    Attachment1,
    InputValidationError,
    delivery_dates,
    fill_result2_workbook,
    inspect_template,
    read_attachment1,
    read_attachment2,
    write_json,
)
from prob02_model import (
    ALPHA_EM,
    BLOCKS_PER_DAY,
    C_CAP,
    DAILY_DELIVERY_START,
    DAYS_FULL,
    DELTA_T,
    E_INIT,
    E_MAX,
    E_MIN,
    ETA_CH,
    ETA_DIS,
    ETA_ROUND_TRIP,
    P_MAX,
    PERIODS_PER_DAY,
    Q_CAP,
    SPEC_DATES,
    TABLE1_SLOTS,
    LpData,
    LpSolution,
    emergency_intervals,
    evaluate,
    solve_lp,
    state_series,
)

PROJECT_MARKERS = ("pyproject.toml", "AGENTS.md")
DELIVERY_LAST_DAY = 364                 # 0 基日索引：2025-12-31
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
    parser = argparse.ArgumentParser(
        description="prob02 计划购电 LP 求解器（assumption_v001 / formulation_v001，M1 主口径）"
    )
    parser.add_argument("--data", default="data/附件1.xlsx", help="附件 1 路径（只读；只用电价列）")
    parser.add_argument("--data2", default="data/附件2.xlsx", help="附件 2 路径（只读；实际负载/光伏）")
    parser.add_argument("--template", default="data/附件5/result2.xlsx", help="result2.xlsx 模板路径（只读）")
    parser.add_argument("--output", required=True, help="输出目录（必须在 assumption_v001 版本目录内）")
    parser.add_argument("--days", type=int, default=DAYS_FULL, help="优化天数；< 365 为探针模式")
    parser.add_argument("--time-limit", type=float, default=300.0, help="HiGHS 求解时限（秒）")
    return parser.parse_args(argv)


def build_tables(
    solution: LpSolution,
    metrics: dict[str, Any],
    attachment1: Attachment1,
    template_info: dict[str, Any],
    *,
    probe_mode: bool,
) -> dict[str, Any]:
    """构造表 1/表 2/表 3（4 个指定日期）并按 AS01 校验位置口径。

    AS01 要求**两个**标签同时在位：附件 1 第 i 行时间戳 = 区间左端点（如 ``10:00``）；
    ``result2.xlsx`` 第 i 个时段表头 = 完整区间（如 ``10:00-10:10``）。
    """
    labels = attachment1.time_labels
    template_labels = template_info["plan_labels"]
    days = solution.data.days
    purchase_d = solution.daily("b")
    charge_d = solution.daily("c")
    discharge_d = solution.daily("q_dis")
    q_em_d = solution.daily("q_em")
    daily = metrics["daily"]

    table1: dict[str, Any] = {}
    table2: dict[str, Any] = {}
    table3: dict[str, Any] = {}
    covered: list[str] = []
    label_ok = True
    for date_text, day_index in SPEC_DATES:
        if day_index >= days:
            continue
        covered.append(date_text)
        slots: list[dict[str, Any]] = []
        for slot_name, position in TABLE1_SLOTS:
            attachment_label = labels[position - 1]
            template_label = template_labels[position - 1]
            slot_start = slot_name.split("-")[0]
            matches = attachment_label == slot_start and template_label == slot_name
            label_ok = label_ok and matches
            slots.append(
                {
                    "slot": slot_name,
                    "position": position,
                    "attachment_timestamp": attachment_label,
                    "template_label": template_label,
                    "label_matches": bool(matches),
                    "purchase_kwh": round(float(purchase_d[day_index, position - 1]), 6),
                }
            )
        table1[date_text] = {
            "slots": slots,
            "all_day_energy_kwh": daily["purchase_kwh"][day_index],
            "all_day_cost_yuan": daily["cost_total_yuan"][day_index],
            "all_day_plan_cost_yuan": daily["cost_plan_yuan"][day_index],
            "all_day_emergency_cost_yuan": daily["cost_emergency_yuan"][day_index],
        }
        table2[date_text] = {
            "block_charge_kwh": [
                round(float(np.sum(charge_d[day_index, k * 24 : (k + 1) * 24])), 6)
                for k in range(BLOCKS_PER_DAY)
            ],
            "block_discharge_kwh": [
                round(float(np.sum(discharge_d[day_index, k * 24 : (k + 1) * 24])), 6)
                for k in range(BLOCKS_PER_DAY)
            ],
            "storage_0_00_kwh": daily["state_start_kwh"][day_index],
            "storage_24_00_kwh": daily["state_end_kwh"][day_index],
        }
        intervals = emergency_intervals(q_em_d[day_index], labels)
        table3[date_text] = {
            "intervals": intervals,
            "total_kwh": round(float(np.sum(q_em_d[day_index])), 6),
            "paper_text": "无（0 kWh）" if not intervals else "",
        }
    return {
        "spec_dates": covered,
        "table1": table1,
        "table2": table2,
        "table3": table3,
        "table1_label_checks_passed": bool(label_ok),
        "table3_note": (
            "题面表 4 的示例日期 2025/3/1 与 3 个区间及其数值是**格式示例**，不是本问答案；"
            "本问主口径下 Σq_em = 0（定理 T1），表 3 为「无（0 kWh）」。"
        ),
        "probe_mode": probe_mode,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_path = resolve(args.data)
    data2_path = resolve(args.data2)
    template_path = resolve(args.template)
    output_dir = resolve(args.output)
    code_dir = Path(__file__).resolve().parent
    probe_mode = args.days < DAYS_FULL

    if not 2 <= args.days <= DAYS_FULL:
        print(f"[prob02] --days 必须在 [2, {DAYS_FULL}]，收到 {args.days}", file=sys.stderr)
        return EXIT_INPUT_INVALID
    try:
        attachment1 = read_attachment1(data_path, expected_rows=PERIODS_PER_DAY)
        attachment2 = read_attachment2(data2_path, expected_days=DAYS_FULL, expected_periods=PERIODS_PER_DAY)
        template_info = inspect_template(template_path)
    except InputValidationError as exc:
        print(f"[prob02] 输入校验失败：{exc}", file=sys.stderr)
        return EXIT_INPUT_INVALID
    if template_info["plan_rows"] < DELIVERY_LAST_DAY + 1 - DAILY_DELIVERY_START:
        print(
            f"[prob02] 模板『{PLAN_SHEET}』只有 {template_info['plan_rows']} 天，"
            f"少于交付期 {DELIVERY_LAST_DAY + 1 - DAILY_DELIVERY_START} 天",
            file=sys.stderr,
        )
        return EXIT_INPUT_INVALID

    days = args.days
    periods = days * PERIODS_PER_DAY
    lp_data = LpData(
        price=np.tile(attachment1.price, days),
        load_energy=attachment2.load_kw[:days].reshape(-1) * DELTA_T,
        pv_energy=attachment2.pv_kw[:days].reshape(-1) * DELTA_T,
        days=days,
    )
    solution = solve_lp(lp_data, time_limit_seconds=args.time_limit)
    run_meta = {
        "problem_id": "microgrid_2025",
        "question_id": "prob02",
        "assumption_version": "assumption_v001",
        "formulation_version": "formulation_v001",
        "stage": "computation",
        "model": "M1",
        "probe_mode": probe_mode,
        "days": days,
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
            "attachment1_md5": attachment1.md5,
            "attachment1_periods": attachment1.periods,
            "attachment2": str(data2_path),
            "attachment2_md5": attachment2.md5,
            "attachment2_days": attachment2.days,
            "template": str(template_path),
            "template_md5": template_info["md5"],
            "template_plan_rows": template_info["plan_rows"],
        },
        "parameters": {
            "delta_t_h": DELTA_T,
            "eta_ch": ETA_CH,
            "eta_dis": ETA_DIS,
            "eta_round_trip": ETA_ROUND_TRIP,
            "alpha_em": 5.0,
            "e_init_kwh": E_INIT,
            "e_min_kwh": E_MIN,
            "e_max_kwh": E_MAX,
            "e_terminal": None,
            "p_max_kw": P_MAX,
            "c_cap_kwh": C_CAP,
            "q_dis_cap_kwh": Q_CAP,
            "b_upper_kwh": None,
        },
        "code_sha256": code_fingerprint(code_dir),
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
    }

    if solution.status != 0:
        write_json(output_dir / "solver_status.json", {
            "status": solution.status,
            "message": solution.message,
            "feasible_incumbent": False,
            "objective_yuan": None,
            "iterations": solution.iterations,
            "device": "cpu",
            "gpu_required": False,
            "seed": None,
        })
        write_json(output_dir / "run_manifest.json", {**run_meta, "outcome": "solver_not_optimal"})
        print(f"[prob02] 求解未达最优：status={solution.status} {solution.message}", file=sys.stderr)
        return EXIT_SOLVER_NOT_OPTIMAL

    metrics = evaluate(solution, full_horizon=not probe_mode)
    tables = build_tables(solution, metrics, attachment1, template_info, probe_mode=probe_mode)
    matrix_scale = {
        "variables": 6 * periods,
        "equality_constraints": 2 * periods,
        "variable_bounds": 6 * periods,
        "nonzero": 9 * periods - 1,
        "integer_variables": 0,
    }

    write_json(output_dir / "solver_status.json", {
        "status": solution.status,
        "message": solution.message,
        "solver": "highs",
        "iterations": solution.iterations,
        "objective_yuan": metrics["objective_yuan"],
        "delivery_cost_yuan": metrics["delivery_cost_yuan"],
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
        "objective_plan_yuan": metrics["objective_plan_yuan"],
        "objective_emergency_yuan": metrics["objective_emergency_yuan"],
        "delivery_cost_yuan": metrics["delivery_cost_yuan"],
        "january_cost_yuan": metrics["january_cost_yuan"],
        "totals": metrics["totals"],
        "identities": metrics["identities"],
        "daily": metrics["daily"],
        "checks": metrics["checks"],
        "checks_failed": metrics["checks_failed"],
        "series": metrics["series"],
    })
    write_json(output_dir / "tables.json", tables)

    delivery_dates_list = delivery_dates(attachment2.dates, DAILY_DELIVERY_START)[: max(days - DAILY_DELIVERY_START, 0)]
    workbook_name = "probe_result2.xlsx" if probe_mode else "result2.xlsx"
    workbook_info: dict[str, Any] | None = None
    if delivery_dates_list:
        selected = slice(DAILY_DELIVERY_START, days)
        purchase_d = solution.daily("b")
        charge_d = solution.daily("c")
        discharge_d = solution.daily("q_dis")
        q_em_d = solution.daily("q_em")
        price_d = lp_data.price.reshape(days, PERIODS_PER_DAY)
        state = state_series(solution)
        day_cost = np.sum(price_d * purchase_d, axis=1) + np.sum(ALPHA_EM * price_d * q_em_d, axis=1)
        workbook_info = fill_result2_workbook(
            template=template_path,
            dest=output_dir / workbook_name,
            dates=delivery_dates_list,
            purchase_kwh=purchase_d[selected],
            charge_kwh=charge_d[selected],
            discharge_kwh=discharge_d[selected],
            state_start_kwh=state[:periods:PERIODS_PER_DAY][selected],
            state_end_kwh=state[PERIODS_PER_DAY::PERIODS_PER_DAY][selected],
            day_energy_kwh=np.sum(purchase_d, axis=1)[selected],
            day_cost_yuan=day_cost[selected],
            emergency_intervals=[
                [
                    (item["slot"], item["energy_kwh"])
                    for item in emergency_intervals(q_em_d[index], attachment1.time_labels)
                ]
                for index in range(DAILY_DELIVERY_START, days)
            ],
        )

    failed = list(metrics["checks_failed"])
    if not tables["table1_label_checks_passed"]:
        failed.append("table1_label_checks")
    if workbook_info is not None and workbook_info.get("format_residuals"):
        failed.append("result2_format_residuals")
    write_json(output_dir / "run_manifest.json", {
        **run_meta,
        "outcome": "hard_check_failed" if failed else "completed",
        "matrix_scale": matrix_scale,
        "workbook": workbook_name if delivery_dates_list else None,
        "workbook_info": workbook_info,
        "delivery_days": len(delivery_dates_list),
        "checks_failed": failed,
        "objective_yuan": metrics["objective_yuan"],
        "delivery_cost_yuan": metrics["delivery_cost_yuan"],
        "total_purchase_kwh": metrics["totals"]["total_purchase_kwh"],
        "total_q_em_kwh": metrics["totals"]["total_q_em_kwh"],
        "total_spill_kwh": metrics["totals"]["total_spill_kwh"],
        "storage_final_kwh": metrics["totals"]["storage_final_kwh"],
    })

    print(
        f"[prob02] {'探针' if probe_mode else '正式'}运行完成：days={days} periods={periods} "
        f"C_total={metrics['objective_yuan']:.4f} 元，交付期={metrics['delivery_cost_yuan']:.4f} 元，"
        f"Σb={metrics['totals']['total_purchase_kwh']:.4f} kWh，Σq_em={metrics['totals']['total_q_em_kwh']:.6f} kWh，"
        f"Σs={metrics['totals']['total_spill_kwh']:.4f} kWh，失败检查={failed}"
    )
    if failed:
        print(f"[prob02] 硬检查未通过：{failed}", file=sys.stderr)
        return EXIT_HARD_CHECK_FAILED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
