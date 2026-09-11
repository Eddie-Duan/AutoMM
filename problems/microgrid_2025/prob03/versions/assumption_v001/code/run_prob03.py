# -*- coding: utf-8 -*-
"""prob03 计算入口：读取附件 1/2/3，执行 ``M1`` 三层顺序向前递推，写出 ``result3.xlsx`` 与追踪产物。

用法（正式任务，由 computation 阶段的 resource-manager 通过 ``scripts/compute_dispatcher.py`` 提交）::

    <venv>/python run_prob03.py --data data/附件1.xlsx --data2 data/附件2.xlsx --data3 data/附件3.xlsx \\
        --template data/附件5/result3.xlsx \\
        --output problems/microgrid_2025/prob03/versions/assumption_v001/results/<run> \\
        --days 365 --time-limit 60

探针模式（``--days`` 小于 365）只用于接口自检：不写 ``result3.xlsx``，改写 ``probe_result3.xlsx``，
并跳过解析界与量级检查。完整计算必须由 Runner/tasks.py 创建隔离 task（supervised worker）执行。

口径（不得逐问更改）：主口径 ``M1``（团队裁定 B0）；目标 ``C_total = C_plan + C_em + C_adj``（元，不带 Δt，D9）；
``c ≤ 833.3333``、``q_dis ≤ 750.0000``（D10 口径丙 / E1）、``E ∈ [1200,10800]``、``E_{1/1,0} = 6000``、终端自由；
统一 tie-breaking（团队 T7-1）：所有层一律 ``min [层主目标] + ε·Σ_t(c+q_dis)``，逐层落盘 T7-2 不变性验证与
T7-3 退化/多重最优审计（``t7_tiebreak.json``）。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from prob03_io import (
    DECISION_HOURS,
    PLAN_SHEET,
    Attachment1,
    InputValidationError,
    delivery_dates,
    fill_result3_workbook,
    inspect_template,
    read_attachment1,
    read_attachment2,
    read_attachment3,
    write_json,
)
from prob03_model import (
    ALPHA_EM,
    BETA_DEF,
    BETA_OVER,
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
    T7_EPS_RELATIVE,
    T7_INVARIANCE_TOL,
    T7_MAX_SHRINKS,
    T7_SHRINK_FACTOR,
    T7_TIEBREAK_RULE,
    TABLE1_SLOTS,
    BudgetExceeded,
    ChainInputs,
    LayerFailure,
    M1Result,
    cross_year_dropped_count,
    downscale,
    emergency_intervals,
    evaluate,
    run_m1,
    state_starts,
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
        description=(
            "prob03 计划/调整/结算三层顺序 LP 求解器（assumption_v001 / formulation_v001，M1 主口径；"
            "统一 tie-breaking = 团队 T7）"
        )
    )
    parser.add_argument("--data", default="data/附件1.xlsx", help="附件 1 路径（只读；只用电价列）")
    parser.add_argument("--data2", default="data/附件2.xlsx", help="附件 2 路径（只读；实际负载/光伏）")
    parser.add_argument("--data3", default="data/附件3.xlsx", help="附件 3 路径（只读；整点光伏预报）")
    parser.add_argument("--template", default="data/附件5/result3.xlsx", help="result3.xlsx 模板路径（只读）")
    parser.add_argument("--output", required=True, help="输出目录（必须在 assumption_v001 版本目录内）")
    parser.add_argument("--days", type=int, default=DAYS_FULL, help="优化天数；< 365 为探针模式")
    parser.add_argument("--time-limit", type=float, default=60.0, help="**单层** LP 的 HiGHS 时限（秒）")
    parser.add_argument("--max-wall-seconds", type=float, default=3300.0, help="整条链的墙钟预算（秒）")
    return parser.parse_args(argv)


def build_layer_inputs(attachment3: Any, days: int) -> tuple[dict[int, np.ndarray], dict[str, Any]]:
    """按 AS05 生成各决策时刻的降尺度预报矩阵，并记录层输入指纹与支配/跨年结构。"""
    forecast: dict[int, np.ndarray] = {}
    info: dict[str, Any] = {}
    for hour in DECISION_HOURS:
        matrix = np.vstack([downscale(attachment3.row(day, hour), hour) for day in range(days)])
        forecast[hour] = matrix
        finite = int(np.count_nonzero(np.isfinite(matrix)))
        digest = hashlib.sha256(np.round(matrix[np.isfinite(matrix)], 6).tobytes()).hexdigest()
        info[f"hour_{hour}"] = {
            "dominated_periods_per_day": PERIODS_PER_DAY - 6 * hour,
            "finite_cells": finite,
            "nan_cells": int(matrix.size - finite),
            "expected_nan_cells": 6 * hour * days,
            "cross_year_dropped_items_per_day": cross_year_dropped_count(hour),
            "forecast_matrix_sha256": digest,
            "uses_actual_pv": False,
        }
    info["dominance_rule"] = (
        "nu(i) = 6*floor((i-1)/36)；D_0/D_6/D_12/D_18 各 36 时段（i<=36 / 37..72 / 73..108 / 109..144）"
    )
    info["downscale_rule"] = (
        "k=1 前向保持 A_{m,1}；k>=2 取 (1-j/6)A_{m,k-1} + (j/6)A_{m,k}；"
        "块能量 (2.5A_{k-1}+3.5A_k)/6（不保块内能量，T3）"
    )
    info["cross_year_dropped_total_per_day"] = sum(cross_year_dropped_count(h) for h in DECISION_HOURS)
    info["actual_pv_scope"] = "settlement_layer_only（§0.4 F2：决策层输入不含 PV^act）"
    return forecast, info


def build_tables(
    result: M1Result,
    metrics: dict[str, Any],
    attachment1: Attachment1,
    template_info: dict[str, Any],
    *,
    probe_mode: bool,
) -> dict[str, Any]:
    """构造表 1/表 2/表 3（4 个指定日期）并按 AS01 校验位置口径。"""
    labels = attachment1.time_labels
    template_labels = template_info["plan_labels"]
    days = result.days
    q = result.q
    c = result.c
    q_dis = result.q_dis
    q_em = result.q_em
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
            matches = attachment_label == slot_name.split("-")[0] and template_label == slot_name
            label_ok = label_ok and matches
            slots.append(
                {
                    "slot": slot_name,
                    "position": position,
                    "attachment_timestamp": attachment_label,
                    "template_label": template_label,
                    "label_matches": bool(matches),
                    "final_purchase_kwh": round(float(q[day_index, position - 1]), 6),
                }
            )
        table1[date_text] = {
            "slots": slots,
            "all_day_energy_kwh": daily["purchase_kwh"][day_index],
            "all_day_cost_yuan": daily["cost_total_yuan"][day_index],
            "all_day_plan_cost_yuan": daily["cost_plan_yuan"][day_index],
            "all_day_adjust_cost_yuan": daily["cost_adj_yuan"][day_index],
            "all_day_emergency_cost_yuan": daily["cost_em_yuan"][day_index],
        }
        table2[date_text] = {
            "block_charge_kwh": [
                round(float(np.sum(c[day_index, k * 24 : (k + 1) * 24])), 6) for k in range(BLOCKS_PER_DAY)
            ],
            "block_discharge_kwh": [
                round(float(np.sum(q_dis[day_index, k * 24 : (k + 1) * 24])), 6) for k in range(BLOCKS_PER_DAY)
            ],
            "storage_0_00_kwh": daily["state_start_kwh"][day_index],
            "storage_24_00_kwh": daily["state_end_kwh"][day_index],
        }
        intervals = emergency_intervals(q_em[day_index], labels)
        table3[date_text] = {
            "intervals": intervals,
            "total_kwh": round(float(np.sum(q_em[day_index])), 6),
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
            "本问紧急购电由预报—实际光伏误差驱动（结算层），表 3 按 D11-A 合并连续时段并以左端点标签填报。"
        ),
        "table2_note": (
            "表 2 的 0:00/24:00 为计划窗首/末状态（AS01 左端点口径使计划窗为 0:10→24:10，模板固有相位）；"
            "prob03 为多日滚动切片，E_{d,0} = E_{d−1,144} 随日变化（团队勘误 R1），与 prob01 单日周期端点恒 6000 不同。"
        ),
        "probe_mode": probe_mode,
    }


def build_t7_audit(result: M1Result, metrics: dict[str, Any], *, days: int) -> dict[str, Any]:
    """团队 T7 的落盘审计：逐层不变性验证（T7-2）+ 退化维度与多重最优（T7-3）。"""
    records = [item.as_dict() for item in result.tiebreak_records]
    checks = [item for item in metrics["checks"] if item["name"].startswith("t7_")]
    return {
        "policy": "T7（团队裁定：统一冻结 tie-breaking，效力高于 B4-C5 初版措辞）",
        "rule": T7_TIEBREAK_RULE,
        "epsilon_definition": (
            "ε = T7_EPS_RELATIVE × max(|该层主目标最优值|, 1) / [n·(c_cap + q_dis_cap)]"
        ),
        "eps_relative": T7_EPS_RELATIVE,
        "invariance_tol": T7_INVARIANCE_TOL,
        "shrink_factor": T7_SHRINK_FACTOR,
        "max_shrinks": T7_MAX_SHRINKS,
        "days": days,
        "layers": len(records),
        "plan_layers": int(sum(1 for item in result.tiebreak_records if item.layer == "plan")),
        "adjustment_layers": int(sum(1 for item in result.tiebreak_records if item.layer == "adjustment")),
        "summary": metrics["t7_tiebreak"],
        "checks": checks,
        "checks_failed": [item["name"] for item in checks if not item["passed"]],
        "per_layer": records,
        "m8_fairness_note": (
            "T7-5：ablation 的 M2–M8（尤其 M8 独立第二实现）必须复用 prob03_model._solve_with_tiebreak / "
            "tiebreak_epsilon / throughput_coefficients，tie-breaking 规则须与 M1 完全一致，"
            "仅允许在 HiGHS 设置（presolve、消元顺序）上不同。"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_path = resolve(args.data)
    data2_path = resolve(args.data2)
    data3_path = resolve(args.data3)
    template_path = resolve(args.template)
    output_dir = resolve(args.output)
    code_dir = Path(__file__).resolve().parent
    probe_mode = args.days < DAYS_FULL

    if not 2 <= args.days <= DAYS_FULL:
        print(f"[prob03] --days 必须在 [2, {DAYS_FULL}]，收到 {args.days}", file=sys.stderr)
        return EXIT_INPUT_INVALID
    days = args.days

    try:
        attachment1 = read_attachment1(data_path, expected_rows=PERIODS_PER_DAY)
        attachment2 = read_attachment2(data2_path, expected_days=DAYS_FULL, expected_periods=PERIODS_PER_DAY)
        attachment3 = read_attachment3(data3_path, expected_days=DAYS_FULL)
        template_info = inspect_template(template_path)
    except InputValidationError as exc:
        print(f"[prob03] 输入校验失败：{exc}", file=sys.stderr)
        return EXIT_INPUT_INVALID

    if attachment3.dates != attachment2.dates:
        print("[prob03] 附件 3 与附件 2 的日期序列不一致", file=sys.stderr)
        return EXIT_INPUT_INVALID
    delivery_days_expected = max(DELIVERY_LAST_DAY + 1 - DAILY_DELIVERY_START, 0)
    if template_info["plan_rows"] < delivery_days_expected:
        print(
            f"[prob03] 模板『{PLAN_SHEET}』只有 {template_info['plan_rows']} 天，"
            f"少于交付期 {delivery_days_expected} 天",
            file=sys.stderr,
        )
        return EXIT_INPUT_INVALID

    forecast, layer_inputs = build_layer_inputs(attachment3, days)
    for hour in DECISION_HOURS:
        info = layer_inputs[f"hour_{hour}"]
        if info["nan_cells"] != info["expected_nan_cells"]:
            print(f"[prob03] 降尺度覆盖域异常：hour={hour} nan={info['nan_cells']}", file=sys.stderr)
            return EXIT_INPUT_INVALID
        dominated = np.where(np.isfinite(forecast[hour][0]))[0]
        if not np.isfinite(forecast[hour][:, dominated]).all():
            print(f"[prob03] 降尺度预报在支配域含 NaN：hour={hour}", file=sys.stderr)
            return EXIT_INPUT_INVALID

    chain = ChainInputs(
        days=days,
        price=np.tile(attachment1.price, (days, 1)),
        load_energy=attachment2.load_kw[:days] * DELTA_T,
        pv_act_energy=attachment2.pv_kw[:days] * DELTA_T,
        forecast_kw=forecast,
    )
    run_meta = {
        "problem_id": "microgrid_2025",
        "question_id": "prob03",
        "assumption_version": "assumption_v001",
        "formulation_version": "formulation_v001",
        "stage": "computation",
        "model": "M1",
        "probe_mode": probe_mode,
        "days": days,
        "periods": days * PERIODS_PER_DAY,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_id": os.environ.get("AUTOMM_TASK_ID"),
        "output_directory": str(output_dir),
        "device": "cpu",
        "gpu_required": False,
        "seed": None,
        "deterministic": True,
        "solver": "scipy.optimize.linprog(method='highs')",
        "layer_time_limit_seconds": args.time_limit,
        "max_wall_seconds": args.max_wall_seconds,
        "input": {
            "attachment1": str(data_path),
            "attachment1_md5": attachment1.md5,
            "attachment1_periods": attachment1.periods,
            "attachment2": str(data2_path),
            "attachment2_md5": attachment2.md5,
            "attachment2_days": attachment2.days,
            "attachment3": str(data3_path),
            "attachment3_md5": attachment3.md5,
            "attachment3_days": attachment3.days,
            "template": str(template_path),
            "template_md5": template_info["md5"],
            "template_plan_rows": template_info["plan_rows"],
        },
        "parameters": {
            "delta_t_h": DELTA_T,
            "eta_ch": ETA_CH,
            "eta_dis": ETA_DIS,
            "eta_round_trip": ETA_ROUND_TRIP,
            "alpha_em": ALPHA_EM,
            "beta_def": BETA_DEF,
            "beta_over": BETA_OVER,
            "e_init_kwh": E_INIT,
            "e_min_kwh": E_MIN,
            "e_max_kwh": E_MAX,
            "e_terminal": None,
            "p_max_kw": P_MAX,
            "c_cap_kwh": C_CAP,
            "q_dis_cap_kwh": Q_CAP,
            "b_upper_kwh": None,
            "decision_hours": list(DECISION_HOURS),
        },
        "layer_inputs": layer_inputs,
        "code_sha256": code_fingerprint(code_dir),
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
    }
    # 每层名义 LP 次数（T7 四段式，与 implementation.md §2.1 / task_spec.yaml 的 5,840 一致）：
    # ① 纯主目标基线（T7-2 的「加入前」）② T7-1 字面加权式 ③ 字典序提交解（主目标最优面上最小吞吐量）
    # ④ T7-3 最优面退化探测；T7-2 每触发一次 ε 收缩另加 1 次（有界于 T7_MAX_SHRINKS=8）。
    solver_calls_per_layer = 4
    matrix_scale = {
        "plan_layer": {"variables": 720, "equality_constraints": 288, "inequalities": 0,
                       "solver_calls_nominal": solver_calls_per_layer},
        "adjustment_layer_m6": {"variables": 756, "equality_constraints": 216, "inequalities": 216,
                                "solver_calls_nominal": solver_calls_per_layer},
        "adjustment_layer_m12": {"variables": 504, "equality_constraints": 144, "inequalities": 144,
                                 "solver_calls_nominal": solver_calls_per_layer},
        "adjustment_layer_m18": {"variables": 252, "equality_constraints": 72, "inequalities": 72,
                                 "solver_calls_nominal": solver_calls_per_layer},
        "per_day": {"variables": 2232, "equality_constraints": 720, "inequalities": 432,
                    "layer_solves": 4, "solver_calls_nominal": 4 * solver_calls_per_layer},
        "lp_calls_total": 4 * days,
        "lp_solver_invocations_nominal": 4 * days * solver_calls_per_layer,
        "tiebreak_solver_calls_per_layer_nominal": solver_calls_per_layer,
        "tiebreak_extra_calls_note": (
            "T7-2 不变性不满足时每个缩小一次 ε 会额外增加一次 LP（有界于 T7_MAX_SHRINKS）；"
            "实际调用次数见 run_manifest.t7_tiebreak.total_shrinks。"
        ),
        "integer_variables_main": 0,
    }

    started = time.perf_counter()
    try:
        result = run_m1(chain, time_limit_seconds=args.time_limit, deadline=started + args.max_wall_seconds)
    except (LayerFailure, BudgetExceeded) as exc:
        status = getattr(exc, "status", -1)
        write_json(
            output_dir / "solver_status.json",
            {
                "status": int(status),
                "message": str(exc),
                "feasible_incumbent": False,
                "model": "M1",
                "device": "cpu",
                "gpu_required": False,
                "seed": None,
                "seconds": time.perf_counter() - started,
            },
        )
        write_json(
            output_dir / "run_manifest.json",
            {**run_meta, "outcome": "solver_not_optimal", "matrix_scale": matrix_scale},
        )
        print(f"[prob03] 求解未达最优：{exc}", file=sys.stderr)
        return EXIT_SOLVER_NOT_OPTIMAL
    elapsed = time.perf_counter() - started

    metrics = evaluate(result, full_horizon=not probe_mode)
    tables = build_tables(result, metrics, attachment1, template_info, probe_mode=probe_mode)
    t7_audit = build_t7_audit(result, metrics, days=days)

    write_json(
        output_dir / "solver_status.json",
        {
            "status": 0,
            "message": "all layers optimal",
            "solver": "highs",
            "model": "M1",
            "objective_yuan": metrics["objective_yuan"],
            "delivery_cost_yuan": metrics["delivery"]["cost_total_yuan"],
            "feasible_incumbent": True,
            "mip_gap": None,
            "device": "cpu",
            "gpu_required": False,
            "seed": None,
            "lp_calls": len(result.layer_records),
            "lp_solver_invocations_nominal": matrix_scale["lp_solver_invocations_nominal"],
            "t7_tiebreak": t7_audit["summary"],
            "layer_status_max": max((item.status for item in result.layer_records), default=0),
            "layer_equality_residual_max": max(
                (item.equality_residual_max for item in result.layer_records), default=0.0
            ),
            "layer_equality_residual_relative_max": max(
                (item.equality_residual_relative_max for item in result.layer_records), default=0.0
            ),
            "layer_inequality_residual_max": max(
                (item.inequality_residual_max for item in result.layer_records), default=0.0
            ),
            "layer_inequality_residual_relative_max": max(
                (item.inequality_residual_relative_max for item in result.layer_records), default=0.0
            ),
            "layer_bound_violation_max": max(
                (item.bound_violation_max for item in result.layer_records), default=0.0
            ),
            "layer_seconds_total": (
                float(np.sum([item.seconds for item in result.layer_records])) if result.layer_records else 0.0
            ),
            "wall_seconds": elapsed,
            "deterministic": True,
        },
    )
    write_json(
        output_dir / "solution.json",
        {
            "objective_yuan": metrics["objective_yuan"],
            "cost_plan_yuan": metrics["cost_plan_yuan"],
            "cost_adj_yuan": metrics["cost_adj_yuan"],
            "cost_em_yuan": metrics["cost_em_yuan"],
            "delivery": metrics["delivery"],
            "totals": metrics["totals"],
            "identities": metrics["identities"],
            "bounds": metrics["bounds"],
            "statistics": metrics["statistics"],
            "daily": metrics["daily"],
            "checks": metrics["checks"],
            "checks_failed": metrics["checks_failed"],
            "t7_tiebreak": t7_audit["summary"],
            "layer_summary": [item.as_dict() for item in result.layer_records],
            "series": metrics["series"],
        },
    )
    write_json(output_dir / "tables.json", tables)
    write_json(output_dir / "t7_tiebreak.json", t7_audit)

    delivery_dates_list = delivery_dates(attachment2.dates, DAILY_DELIVERY_START)[: max(days - DAILY_DELIVERY_START, 0)]
    workbook_name = "probe_result3.xlsx" if probe_mode else "result3.xlsx"
    workbook_info: dict[str, Any] | None = None
    if delivery_dates_list:
        selected = slice(DAILY_DELIVERY_START, days)
        b = result.plan_b[selected]
        q = result.q[selected]
        c = result.c[selected]
        q_dis = result.q_dis[selected]
        q_em_d = result.q_em[selected]
        starts = state_starts(result)[selected]
        ends = result.E[:, -1][selected]
        price_raw = chain.price[selected]
        dev_plus = np.maximum(b - q, 0.0)
        dev_minus = np.maximum(q - b, 0.0)
        cost_total_d = (
            np.sum(price_raw * b, axis=1)
            + np.sum(price_raw * (BETA_DEF * dev_plus + BETA_OVER * dev_minus), axis=1)
            + np.sum(ALPHA_EM * price_raw * q_em_d, axis=1)
        )
        workbook_info = fill_result3_workbook(
            template=template_path,
            dest=output_dir / workbook_name,
            dates=delivery_dates_list,
            planned_kwh=b,
            adjusted_kwh=q,
            charge_kwh=c,
            discharge_kwh=q_dis,
            state_start_kwh=starts,
            state_end_kwh=ends,
            day_energy_planned_kwh=np.sum(b, axis=1),
            day_energy_adjusted_kwh=np.sum(q, axis=1),
            day_cost_yuan=cost_total_d,
            emergency_intervals=[
                [
                    (item["slot"], item["energy_kwh"])
                    for item in emergency_intervals(q_em_d[index], attachment1.time_labels)
                ]
                for index in range(len(delivery_dates_list))
            ],
        )

    failed = list(metrics["checks_failed"])
    if not tables["table1_label_checks_passed"]:
        failed.append("table1_label_checks")
    if workbook_info is not None and workbook_info.get("format_residuals"):
        failed.append("result3_format_residuals")
    write_json(
        output_dir / "run_manifest.json",
        {
            **run_meta,
            "outcome": "hard_check_failed" if failed else "completed",
            "matrix_scale": matrix_scale,
            "lp_calls": len(result.layer_records),
            "lp_solver_invocations_nominal": matrix_scale["lp_solver_invocations_nominal"],
            "t7_tiebreak": t7_audit["summary"],
            "t7_tiebreak_artifact": "t7_tiebreak.json",
            "wall_seconds": elapsed,
            "workbook": workbook_name if delivery_dates_list else None,
            "workbook_info": workbook_info,
            "delivery_days": len(delivery_dates_list),
            "checks_failed": failed,
            "statistics": metrics["statistics"],
            "objective_yuan": metrics["objective_yuan"],
            "cost_plan_yuan": metrics["cost_plan_yuan"],
            "cost_adj_yuan": metrics["cost_adj_yuan"],
            "cost_em_yuan": metrics["cost_em_yuan"],
            "delivery_cost_yuan": metrics["delivery"]["cost_total_yuan"],
            "total_purchase_kwh": metrics["delivery"]["total_purchase_kwh"],
            "total_q_em_kwh": metrics["delivery"]["total_q_em_kwh"],
            "total_spill_kwh": metrics["delivery"]["total_spill_kwh"],
            "storage_final_kwh": metrics["totals"]["storage_final_kwh"],
        },
    )

    print(
        f"[prob03] {'探针' if probe_mode else '正式'}运行完成：days={days} periods={days * PERIODS_PER_DAY} "
        f"LP={len(result.layer_records)} C_total={metrics['objective_yuan']:.4f} 元，"
        f"交付期={metrics['delivery']['cost_total_yuan']:.4f} 元，"
        f"Σb={metrics['totals']['total_plan_kwh']:.4f} kWh，Σq={metrics['totals']['total_purchase_kwh']:.4f} kWh，"
        f"Σq_em={metrics['totals']['total_q_em_kwh']:.6f} kWh，Σs'={metrics['totals']['total_spill_kwh']:.4f} kWh，"
        f"T7主目标最大相对变化={metrics['t7_tiebreak']['max_primary_relative_change']:.3e}"
        f"（阈值 {T7_INVARIANCE_TOL:.0e}，全部通过={metrics['t7_tiebreak']['all_layers_invariance_passed']}），"
        f"吞吐量 {metrics['t7_tiebreak']['throughput_primary_only_kwh']:.4f}→"
        f"{metrics['t7_tiebreak']['throughput_tiebreak_kwh']:.4f} kWh，"
        f"失败检查={failed}"
    )
    if failed:
        print(f"[prob03] 硬检查未通过：{failed}", file=sys.stderr)
        return EXIT_HARD_CHECK_FAILED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
