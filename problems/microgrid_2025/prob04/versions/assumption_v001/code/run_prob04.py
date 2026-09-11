# -*- coding: utf-8 -*-
"""prob04 计算入口：链 ``4-2``（≙ 重算问题 2）与链 ``4-3``（≙ 重算问题 3）的统一 CLI。

用法（正式任务，由 computation 阶段的 resource-manager 通过 ``scripts/compute_dispatcher.py`` 提交）::

    <venv>/python run_prob04.py --chain 4-2 \\
        --data2 data/附件2.xlsx --data4 data/附件4.xlsx \\
        --template42 data/附件5/result4-2.xlsx \\
        --output problems/microgrid_2025/prob04/versions/assumption_v001/results/<run> \\
        --days 365 --time-limit 60 --max-wall-seconds 1500
    <venv>/python run_prob04.py --chain 4-3 --data3 data/附件3.xlsx --template43 data/附件5/result4-3.xlsx ...

探针模式（``--days`` 小于 365）只用于接口自检：不写 ``result4-2.xlsx``/``result4-3.xlsx``，改写
``probe_result4-2.xlsx``/``probe_result4-3.xlsx``，``run_manifest.probe_mode=true``，跳过「解析界/量级带」
四项硬检查，并在 stdout 显式说明。完整计算必须由 Runner/tasks.py 创建隔离 task（supervised worker）执行。

口径（不得逐问更改）：``A8-(b)`` —— 0:00 **不见**当天实时电价，决策层一律用 `\\hat p`（历史实际价
+ 预测器，主口径 ``PF-PERSIST``），结算层一律用附件 4 实际价；``4-3`` 的调整层按 ``κ_m`` 滚动更新；
目标 ``C_total = C_plan (+ C_adj) + C_em``（元，**不乘 Δt**）；``c ≤ 833.3333``、``q_dis ≤ 750.0000``、
``E ∈ [1200, 10800]``、``E_{1/1,0} = 6000``、终端自由；统一 tie-break（AS21，承 prob03 T7-1/T9）。

**禁止**出现「全天电价已知」类表述（``A8-(b)`` 派生⑤）；本文件与全部产物均按「决策—结算分离」陈述。
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
from prob04_io import (
    DAYS_FULL,
    DECISION_HOURS,
    PLAN_SHEET,
    Attachment2,
    Attachment4,
    InputValidationError,
    fill_result42_workbook,
    fill_result43_workbook,
    inspect_template42,
    inspect_template43,
    read_attachment2,
    read_attachment3,
    read_attachment4_price,
    write_json,
)
from prob04_model import (
    ALPHA_EM,
    BETA_DEF,
    BETA_OVER,
    BLOCKS_PER_DAY,
    C_CAP,
    COMMIT_BLOCK,
    D_REQ_START,
    DAILY_MAGNITUDE_BAND_YUAN,
    DELIVERY_MAGNITUDE_BAND_YUAN,
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
    ChainResult,
    LayerFailure,
    block_energy_bias,
    cross_year_dropped_count,
    downscale,
    emergency_intervals,
    evaluate,
    run_chain_42,
    run_chain_43,
    solve_a2_pre,
    state_starts,
)
from prob04_predict import (
    ALL_METHODS,
    DUAL_RECENT_DAYS,
    FALLBACK_CONSTANT_PRICE,
    KAPPA_LOWER,
    KAPPA_UPPER,
    PRIMARY_METHOD,
    predict,
    roll_backtest,
)

PROJECT_MARKERS = ("pyproject.toml", "AGENTS.md")
EXIT_OK = 0
EXIT_SOLVER_NOT_OPTIMAL = 2
EXIT_INPUT_INVALID = 3
EXIT_HARD_CHECK_FAILED = 4
CHAIN_42 = "4-2"
CHAIN_43 = "4-3"
# 跨年（不消费）预报项的 k 区间（formulation §1.4 / §8.4）：m = 6/12/18 分别丢弃 6/12/18 项，合计 36。
CROSS_YEAR_DROPPED_RANGE: dict[int, tuple[int, int]] = {6: (19, 24), 12: (13, 24), 18: (7, 24)}


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
            "prob04 求解器：链 4-2（逐日计划 LP，≙ 重算问题 2）与链 4-3（0:00 计划 + 6:00/12:00/18:00 "
            "调整 + 0.5×/1.5× 偏差结算，≙ 重算问题 3）；assumption_v001 / formulation_v001；"
            "决策—结算分离（A8-(b)），主预测器 PF-PERSIST，统一 tie-break = AS21"
        )
    )
    parser.add_argument("--chain", choices=(CHAIN_42, CHAIN_43), required=True, help="交付链：4-2 或 4-3")
    parser.add_argument("--data2", default="data/附件2.xlsx", help="附件 2 路径（只读；实际负载/光伏）")
    parser.add_argument("--data4", default="data/附件4.xlsx", help="附件 4 路径（只读；实际实时电价）")
    parser.add_argument("--data3", default="data/附件3.xlsx", help="附件 3 路径（只读；整点光伏预报，仅 4-3）")
    parser.add_argument("--template42", default="data/附件5/result4-2.xlsx", help="result4-2.xlsx 模板（只读）")
    parser.add_argument("--template43", default="data/附件5/result4-3.xlsx", help="result4-3.xlsx 模板（只读）")
    parser.add_argument("--output", required=True, help="输出目录（必须在 assumption_v001 版本目录内）")
    parser.add_argument("--days", type=int, default=DAYS_FULL, help="优化天数；< 365 为探针模式")
    parser.add_argument("--time-limit", type=float, default=60.0, help="**单层** LP 的 HiGHS 时限（秒）")
    parser.add_argument("--max-wall-seconds", type=float, default=1500.0, help="整条链的墙钟预算（秒）")
    parser.add_argument("--model", choices=("main", "a2-pre"), default="main",
                        help="main = 主口径；a2-pre = 4-2 的价格完全预知下界锚点（仅探针/sanity，不进入主结果）")
    return parser.parse_args(argv)


def build_decision_prices(price_act: np.ndarray, days: int) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """构造计划层决策价矩阵（两链共用 ``PF-PERSIST``）并登记 ``H_d = ∅`` 的常量中性价回退。"""
    matrix = np.empty((days, PERIODS_PER_DAY))
    fallbacks: list[dict[str, Any]] = []
    for day in range(days):
        item = predict(price_act, day, PRIMARY_METHOD)
        matrix[day] = np.asarray(item["price"], dtype=float)
        if item["fallback"]:
            fallbacks.append(
                {
                    "day_index": day,
                    "date": "2025-01-01" if day == 0 else None,
                    "marker": str(item["fallback"]),
                    "method": PRIMARY_METHOD,
                    "history_size": int(item["history_size"]),
                    "value": FALLBACK_CONSTANT_PRICE,
                    "scope": "plan_layer_decision_price",
                    "reason": (
                        "H_d = 空集（无前一日），(PF-HIST) 的扩张窗均值无定义；改为常量中性价 "
                        f"{FALLBACK_CONSTANT_PRICE}：平坦价 ⇒ 无套利激励 ⇒ 储能保持 6000 kWh，"
                        "是最少信息的合法选择；不使用未来价格、不使用全量均值；该日不参与回测"
                    ),
                }
            )
    return matrix, fallbacks


def build_layer_inputs(attachment3: Any, days: int) -> tuple[dict[int, np.ndarray], dict[str, Any]]:
    """按 formulation §1.4 生成各决策时刻的降尺度预报矩阵，并记录层输入指纹与跨年结构。"""
    forecast: dict[int, np.ndarray] = {}
    info: dict[str, Any] = {}
    biases = [block_energy_bias(attachment3.row(0, hour), hour) for hour in DECISION_HOURS]
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
            "forecast_source": f"附件 3 的 {hour}:00 发布整点预报（日期列前向填充，团队勘误 prob03 E1）",
            "locked_periods": f"i ≤ {6 * hour}（已提交，本层不再决策）" if hour else "无（计划层支配全天）",
            "initial_state_source": (
                "E_{d-1,144}（前一日已提交链末态）" if hour == 0
                else f"E_{{d,{6 * hour}}}（上一已提交链末态）"
            ),
            "uses_actual_pv": False,
        }
    info["dominance_rule"] = (
        "nu(i) = 6*floor((i-1)/36)；D_0/D_6/D_12/D_18 各 36 时段（i<=36 / 37..72 / 73..108 / 109..144）"
    )
    info["downscale_rule"] = (
        "k=1 前向保持 A_{m,1}；2<=k<=24 取 (1-j/6)A_{m,k-1} + (j/6)A_{m,k}；"
        "k<1（i<=6m）未定义；k>24-m 的跨年项不消费、不截断、不外推"
    )
    info["cross_year_dropped_total_per_day"] = sum(cross_year_dropped_count(h) for h in DECISION_HOURS)
    info["cross_year_dropped_list"] = {
        f"m={hour}": (
            f"k={CROSS_YEAR_DROPPED_RANGE[hour][0]}..{CROSS_YEAR_DROPPED_RANGE[hour][1]}"
            "（→ 2026-01-01 及以后，不消费、不截断、不外推）"
        )
        for hour in (6, 12, 18)
    }
    info["block_energy_non_conservation"] = {
        "disclosure": (
            "块 b 的 6 个时段之和 = (2.5A_{k-1} + 3.5A_k)/6（kWh，k>=2），一般 != A_k·1h："
            "降尺度**不保块内能量**，必须在论文与图注显式披露"
        ),
        "day0_examples": {
            f"m={hour}": bias for hour, bias in zip(DECISION_HOURS, biases, strict=True)
        },
    }
    info["actual_pv_scope"] = "settlement_layer_only（决策层输入不含 PV^act）"
    return forecast, info


def build_tables(
    result: ChainResult,
    metrics: dict[str, Any],
    time_labels: list[str],
    template_labels: list[str],
    *,
    probe_mode: bool,
) -> dict[str, Any]:
    """构造表 1/表 2/表 3（4 个指定日期）并核对列标签与行位置口径（formulation §8.3）。"""
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
            attachment_label = time_labels[position - 1]
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
            "quantity_basis": "final_quantity（4-2: b；4-3: q）",
            "all_day_energy_kwh": daily["purchase_kwh"][day_index],
            "all_day_cost_yuan": daily["cost_total_yuan"][day_index],
            "all_day_plan_cost_yuan": daily["cost_plan_yuan"][day_index],
            "all_day_adjust_cost_yuan": daily["cost_adj_yuan"][day_index],
            "all_day_emergency_cost_yuan": daily["cost_em_yuan"][day_index],
        }
        table2[date_text] = {
            "block_rows": {f"block_{k + 1}": f"{24 * k + 1}..{24 * (k + 1)}" for k in range(BLOCKS_PER_DAY)},
            "block_charge_kwh": [
                round(float(np.sum(c[day_index, k * 24 : (k + 1) * 24])), 6) for k in range(BLOCKS_PER_DAY)
            ],
            "block_discharge_kwh": [
                round(float(np.sum(q_dis[day_index, k * 24 : (k + 1) * 24])), 6) for k in range(BLOCKS_PER_DAY)
            ],
            "storage_0_00_kwh": daily["state_start_kwh"][day_index],
            "storage_24_00_kwh": daily["state_end_kwh"][day_index],
            "charge_discharge_not_netted": True,
        }
        intervals = emergency_intervals(q_em[day_index])
        table3[date_text] = {
            "intervals": intervals,
            "rows": max(len(intervals), 1),
            "total_kwh": round(float(np.sum(q_em[day_index])), 6),
            "paper_text": "无（0 kWh）" if not intervals else "",
        }
    return {
        "chain": result.chain,
        "spec_dates": covered,
        "spec_dates_reference": {name: index for name, index in SPEC_DATES},
        "table1": table1,
        "table2": table2,
        "table3": table3,
        "table1_slot_positions": [position for _, position in TABLE1_SLOTS],
        "table1_label_checks_passed": bool(label_ok),
        "table1_quantity_basis": "final_quantity（4-2 为 b；4-3 为最终量 q）",
        "table1_cost_basis": "全天购电费 = C_total^{act},d（正文另给 C_plan/C_adj/C_em 分项）",
        "table3_note": (
            "题面表 4 的示例日期 2025/3/1 与三个区间及其数值是**格式示例**，不是本问答案；"
            "本表按「连续 q_em>0 时段合并为区间 + 左端点标签 [τ_i, τ_j+10min)」填报，"
            f"每日至少 1 行（J_d = 0 写 {chr(0x2014)}/0）。"
        ),
        "table2_note": (
            "表 2 的 0:00/24:00 为计划窗首/末状态（左端点口径使计划窗为 0:10→24:10，模板固有相位）。"
            "**本题为多日滚动切片：E_{d,0} = E_{d−1,144} 随日变化**，与 prob01 的单日周期口径"
            "（E_{d,0} = E_{d,144} ≡ 6000 kWh）必须显式区分（承 prob02 勘误 R1）；"
            "充电量与放电量分别列示、不冲抵。"
        ),
        "probe_mode": bool(probe_mode),
    }


def build_tiebreak_audit(result: ChainResult, metrics: dict[str, Any], *, days: int) -> dict[str, Any]:
    """AS21 的落盘审计：逐层不变性验证 + 退化维度与多重最优探测。"""
    records = [item.as_dict() for item in result.tiebreak_records]
    checks = [item for item in metrics["checks"] if item["name"].startswith("t7_")]
    return {
        "policy": "AS21（承 prob03 团队裁定 T7-1/T9：统一冻结 tie-break，所有层、所有模型一致）",
        "rule": T7_TIEBREAK_RULE,
        "epsilon_definition": "ε = T7_EPS_RELATIVE × max(|该层主目标最优值|, 1) / [n·(c_cap + q_dis_cap)]",
        "eps_relative": T7_EPS_RELATIVE,
        "invariance_tol": T7_INVARIANCE_TOL,
        "shrink_factor": T7_SHRINK_FACTOR,
        "max_shrinks": T7_MAX_SHRINKS,
        "chain": result.chain,
        "days": days,
        "layers": len(records),
        "plan_layers": int(sum(1 for item in result.tiebreak_records if item.layer.startswith("plan"))),
        "adjustment_layers": int(sum(1 for item in result.tiebreak_records if item.layer.startswith("adjustment"))),
        "summary": metrics["t7_tiebreak"],
        "checks": checks,
        "checks_failed": [item["name"] for item in checks if not item["passed"]],
        "per_layer": records,
        "reuse_note": (
            "AS21 承 prob03 T7-5：本问的 ablation/robustness 对照（A2-PRE、κ1、M4-ter 等）必须复用 "
            "prob04_model._solve_with_tiebreak / tiebreak_epsilon / throughput_coefficients，"
            "tie-break 规则须与主口径完全一致，仅允许在 HiGHS 设置上不同。"
        ),
    }


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = resolve(args.output)
    code_dir = Path(__file__).resolve().parent
    chain = args.chain
    probe_mode = args.days < DAYS_FULL

    if not 2 <= args.days <= DAYS_FULL:
        print(f"[prob04] --days 必须在 [2, {DAYS_FULL}]，收到 {args.days}", file=sys.stderr)
        return EXIT_INPUT_INVALID
    if args.model == "a2-pre" and chain != CHAIN_42:
        print("[prob04] --model a2-pre 仅适用于 --chain 4-2（下界锚点，不进入主结果）", file=sys.stderr)
        return EXIT_INPUT_INVALID
    if args.model == "a2-pre" and not probe_mode:
        print(
            "[prob04] --model a2-pre 只允许在探针模式（--days < 365）下运行：它是 ablation/sanity 的"
            "价格完全预知下界锚点，不得作为主结果",
            file=sys.stderr,
        )
        return EXIT_INPUT_INVALID

    days = args.days
    data2_path = resolve(args.data2)
    data4_path = resolve(args.data4)
    data3_path = resolve(args.data3)
    template42_path = resolve(args.template42)
    template43_path = resolve(args.template43)
    template_path = template42_path if chain == CHAIN_42 else template43_path

    try:
        attachment2: Attachment2 = read_attachment2(data2_path, expected_days=DAYS_FULL)
        attachment4: Attachment4 = read_attachment4_price(data4_path, expected_days=DAYS_FULL)
        if attachment4.time_labels != attachment2.time_labels:
            raise InputValidationError("附件 4 与附件 2 的 144 个时间列标签不一致（相位不同）")
        if attachment4.dates != attachment2.dates:
            raise InputValidationError("附件 4 与附件 2 的日期序列不一致")
        attachment3 = None
        if chain == CHAIN_43:
            attachment3 = read_attachment3(data3_path, expected_days=DAYS_FULL)
            if attachment3.dates != attachment2.dates:
                raise InputValidationError("附件 3 与附件 2 的日期序列不一致")
        template_info = (
            inspect_template42(template42_path) if chain == CHAIN_42
            else inspect_template43(template43_path)
        )
    except InputValidationError as exc:
        print(f"[prob04] 输入校验失败：{exc}", file=sys.stderr)
        return EXIT_INPUT_INVALID

    if template_info["differences"]:
        print(f"[prob04] 模板实测与 formulation 登记值存在差异（以实测为准）：{template_info['differences']}")
    template_labels_key = PLAN_SHEET
    template_labels = template_info["measured"]["purchase"][template_labels_key]["labels"]

    decision_price, fallback_records = build_decision_prices(attachment4.price, days)
    forecast: dict[int, np.ndarray] = {}
    layer_inputs: dict[str, Any] = {
        "plan_layer": {
            "price_source": "PF-PERSIST：\\hat p_{d,i} = p^{act}_{d-1,i}（仅 ≤ d−1 的历史实际价）",
            "price_information_set": "H_d = {d' : d' < d}（显式入参）",
            "load_pv_source": (
                "附件 2 实际负载/光伏（问题 2 无预报机制，D3-A）" if chain == CHAIN_42
                else "负载 = 附件 2 实际；光伏 = 附件 3 的 0:00 发布预报降尺度 Π_0"
            ),
            "locked_periods": "无（计划层支配全天 144 时段）" if chain == CHAIN_42 else "无（提交 D_0 = i ≤ 36）",
            "initial_state_source": "E_{d-1,144}（E_{1/1,0} = 6000）",
        },
        "settlement_layer": {
            "price_source": "附件 4 实际价 p^{act}_{d,i}（唯一价格入口）",
            "pv_source": "附件 2 实际 PV^act（唯一 PV^act 入口）",
            "q_em_definition": "q_em = max(0, −r)，r = q + q_dis + PV^act·Δt − L·Δt − c",
        },
        "future_price_used_in_decision": False,
        "blacklist_note": "全文与全部产物不得出现「全天电价已知」类表述（A8-(b) 派生⑤）",
    }
    if chain == CHAIN_43:
        forecast, chain_layer_inputs = build_layer_inputs(attachment3, days)
        layer_inputs.update(chain_layer_inputs)
        layer_inputs["plan_layer"]["price_source"] = "\\hat p^{(0)}_{d,i} = p^{act}_{d-1,i}（κ_0 ≡ 1）"
        for hour in DECISION_HOURS:
            info = layer_inputs[f"hour_{hour}"]
            if info["nan_cells"] != info["expected_nan_cells"]:
                print(f"[prob04] 降尺度覆盖域异常：hour={hour} nan={info['nan_cells']}", file=sys.stderr)
                return EXIT_INPUT_INVALID
            dominated = np.where(np.isfinite(forecast[hour][0]))[0]
            if not np.isfinite(forecast[hour][:, dominated]).all():
                print(f"[prob04] 降尺度预报在支配域含 NaN：hour={hour}", file=sys.stderr)
                return EXIT_INPUT_INVALID

    decision_prices_used = attachment4.price if args.model == "a2-pre" else decision_price
    build_forecast = forecast if chain == CHAIN_43 else {}

    solver_calls_per_layer = 4
    if chain == CHAIN_42:
        matrix_scale = {
            "plan_layer": {"variables": 6 * PERIODS_PER_DAY, "equality_constraints": 2 * PERIODS_PER_DAY,
                           "inequalities": 0, "solver_calls_nominal": solver_calls_per_layer},
            "per_day": {"variables": 6 * PERIODS_PER_DAY, "equality_constraints": 2 * PERIODS_PER_DAY,
                        "layer_solves": 1, "solver_calls_nominal": solver_calls_per_layer},
            "lp_calls_total": days,
            "lp_solver_invocations_nominal": days * solver_calls_per_layer,
        }
    else:
        matrix_scale = {
            "plan_layer": {"variables": 5 * PERIODS_PER_DAY, "equality_constraints": 2 * PERIODS_PER_DAY,
                           "inequalities": 0, "solver_calls_nominal": solver_calls_per_layer},
            "adjustment_layer_m6": {"variables": 7 * 108, "equality_constraints": 216, "inequalities": 216,
                                    "solver_calls_nominal": solver_calls_per_layer},
            "adjustment_layer_m12": {"variables": 7 * 72, "equality_constraints": 144, "inequalities": 144,
                                     "solver_calls_nominal": solver_calls_per_layer},
            "adjustment_layer_m18": {"variables": 7 * 36, "equality_constraints": 72, "inequalities": 72,
                                     "solver_calls_nominal": solver_calls_per_layer},
            "per_day": {"variables": 2232, "equality_constraints": 720, "inequalities": 432,
                        "layer_solves": 4, "solver_calls_nominal": 4 * solver_calls_per_layer},
            "lp_calls_total": 4 * days,
            "lp_solver_invocations_nominal": 4 * days * solver_calls_per_layer,
        }
    matrix_scale["tiebreak_solver_calls_per_layer_nominal"] = solver_calls_per_layer
    matrix_scale["integer_variables_main"] = 0
    matrix_scale["note"] = (
        "AS21/T7 四段式（基线 + 字面加权诊断 + 字典序提交解 + 退化探测）；"
        "T7-2 每次 ε 收缩另加 1 次（有界于 T7_MAX_SHRINKS）；实际调用次数见 solver_status.lp_calls。"
    )

    chain_inputs = ChainInputs(
        days=days,
        price_act=attachment4.price[:days],
        decision_price=decision_prices_used[:days],
        load_energy=attachment2.load_kw[:days] * DELTA_T,
        pv_act_energy=attachment2.pv_kw[:days] * DELTA_T,
        forecast_kw=build_forecast,
    )

    started = time.perf_counter()
    result: ChainResult
    try:
        if args.model == "a2-pre":
            result, records, tiebreaks = solve_a2_pre(chain_inputs, time_limit_seconds=args.time_limit)
        elif chain == CHAIN_42:
            result = run_chain_42(chain_inputs, time_limit_seconds=args.time_limit,
                                  deadline=started + args.max_wall_seconds)
        else:
            result = run_chain_43(chain_inputs, time_limit_seconds=args.time_limit,
                                  deadline=started + args.max_wall_seconds)
    except (LayerFailure, BudgetExceeded) as exc:
        status = getattr(exc, "status", -1)
        write_json(
            output_dir / "solver_status.json",
            {
                "status": int(status),
                "message": str(exc),
                "feasible_incumbent": False,
                "chain": chain,
                "model": args.model,
                "device": "cpu",
                "gpu_required": False,
                "seed": None,
                "days": days,
                "probe_mode": probe_mode,
                "seconds": time.perf_counter() - started,
            },
        )
        write_json(
            output_dir / "run_manifest.json",
            {
                "problem_id": "microgrid_2025",
                "question_id": "prob04",
                "assumption_version": "assumption_v001",
                "formulation_version": "formulation_v001",
                "stage": "computation",
                "chain": chain,
                "model": args.model,
                "probe_mode": probe_mode,
                "days": days,
                "outcome": "solver_not_optimal",
                "matrix_scale": matrix_scale,
                "task_id": os.environ.get("AUTOMM_TASK_ID"),
            },
        )
        print(f"[prob04] 求解未达最优：{exc}", file=sys.stderr)
        return EXIT_SOLVER_NOT_OPTIMAL
    elapsed = time.perf_counter() - started

    metrics = evaluate(result, probe_mode=probe_mode, full_horizon=not probe_mode)
    backtest = roll_backtest(attachment4.price, days=DAYS_FULL, methods=ALL_METHODS)
    tables = build_tables(result, metrics, attachment2.time_labels, template_labels, probe_mode=probe_mode)
    tiebreak_audit = build_tiebreak_audit(result, metrics, days=days)

    delivery_index = slice(min(D_REQ_START, days), days)
    delivery_dates_list = attachment2.dates[delivery_index]
    starts = state_starts(result)[delivery_index]
    ends = result.E[:, -1][delivery_index]
    day_cost = np.asarray(metrics["daily"]["cost_total_yuan"], dtype=float)[delivery_index]
    workbook_info: dict[str, Any] | None = None
    if len(delivery_dates_list):
        b_delivery = result.plan_b[delivery_index]
        q_delivery = result.q[delivery_index]
        c_delivery = result.c[delivery_index]
        q_dis_delivery = result.q_dis[delivery_index]
        q_em_delivery = result.q_em[delivery_index]
        intervals = [
            [(item["slot"], item["energy_kwh"]) for item in emergency_intervals(q_em_delivery[index])]
            for index in range(len(delivery_dates_list))
        ]
        wb_prefix = "probe_" if probe_mode else ""
        wb_suffix = "a2-pre_" if args.model == "a2-pre" else ""
        workbook_name = f"{wb_prefix}{wb_suffix}result{chain}.xlsx"
        if chain == CHAIN_42:
            workbook_info = fill_result42_workbook(
                template=template_path,
                dest=output_dir / workbook_name,
                dates=delivery_dates_list,
                purchase_kwh=b_delivery,
                charge_kwh=c_delivery,
                discharge_kwh=q_dis_delivery,
                state_start_kwh=starts,
                state_end_kwh=ends,
                day_energy_kwh=np.sum(b_delivery, axis=1),
                day_cost_yuan=day_cost,
                emergency_intervals=intervals,
            )
        else:
            workbook_info = fill_result43_workbook(
                template=template_path,
                dest=output_dir / workbook_name,
                dates=delivery_dates_list,
                planned_kwh=b_delivery,
                adjusted_kwh=q_delivery,
                charge_kwh=c_delivery,
                discharge_kwh=q_dis_delivery,
                state_start_kwh=starts,
                state_end_kwh=ends,
                day_energy_planned_kwh=np.sum(b_delivery, axis=1),
                day_energy_adjusted_kwh=np.sum(q_delivery, axis=1),
                day_cost_yuan=day_cost,
                emergency_intervals=intervals,
            )
    else:
        workbook_name = None

    failed = list(metrics["checks_failed"])
    if not tables["table1_label_checks_passed"]:
        failed.append("table1_label_checks")
    if workbook_info is not None and workbook_info.get("format_residuals"):
        failed.append("workbook_format_residuals")

    naming = {
        "chain_4-2": (
            "≙ 重算问题 2：逐日 0:00 一次计划 LP（无调整层、无偏差结算）；q ≡ b；"
            "C_total^act = C_plan^act + C_em^act（q_em ≡ 0，§2.3 定理）"
        ),
        "chain_4-3": (
            "≙ 重算问题 3：0:00 计划 + 6:00/12:00/18:00 调整（κ_m 滚动水平校正）+ 0.5×/1.5× 双向偏差结算；"
            "C_total^act = C_plan^act + C_adj^act + C_em^act；结算用 PV^act 与 p^act 的唯一入口"
        ),
        "price_basis": "决策层用 \\hat p（PF-PERSIST / κ_m 滚动更新），结算层一律用附件 4 实际价 p^act",
        "quantity_basis": "run_manifest.total_purchase_kwh 装 Σq（4-2 中 q ≡ b）；stdout 摘要为 D_full 口径",
    }

    run_meta: dict[str, Any] = {
        "problem_id": "microgrid_2025",
        "question_id": "prob04",
        "assumption_version": "assumption_v001",
        "formulation_version": "formulation_v001",
        "stage": "computation",
        "chain": chain,
        "model": args.model,
        "probe_mode": probe_mode,
        "days": days,
        "periods": days * PERIODS_PER_DAY,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_id": os.environ.get("AUTOMM_TASK_ID") or None,
        "output_directory": str(output_dir),
        "device": "cpu",
        "gpu_required": False,
        "seed": None,
        "deterministic": True,
        "solver": "scipy.optimize.linprog(method='highs')",
        "layer_time_limit_seconds": args.time_limit,
        "max_wall_seconds": args.max_wall_seconds,
        "naming": naming,
        "input": {
            "attachment2": str(data2_path),
            "attachment2_md5": attachment2.md5,
            "attachment2_days": attachment2.days,
            "attachment3": str(data3_path) if chain == CHAIN_43 else None,
            "attachment3_md5": attachment3.md5 if attachment3 is not None else None,
            "attachment4": str(data4_path),
            "attachment4_md5": attachment4.md5,
            "attachment4_days": attachment4.days,
            "attachment1_used": False,
            "template": str(template_path),
            "template_md5": template_info["measured"]["md5"],
            "template_measured": template_info["measured"],
            "template_formulation_registered": template_info["formulation_registered"],
            "template_differences": template_info["differences"],
        },
        "parameters": {
            "delta_t_h": DELTA_T,
            "eta_ch": ETA_CH,
            "eta_dis": ETA_DIS,
            "eta_round_trip": ETA_ROUND_TRIP,
            "alpha_em": ALPHA_EM,
            "beta_def": BETA_DEF if chain == CHAIN_43 else None,
            "beta_over": BETA_OVER if chain == CHAIN_43 else None,
            "e_init_kwh": E_INIT,
            "e_min_kwh": E_MIN,
            "e_max_kwh": E_MAX,
            "e_terminal": None,
            "p_max_kw": P_MAX,
            "c_cap_kwh": C_CAP,
            "q_dis_cap_kwh": Q_CAP,
            "b_upper_kwh": None,
            "decision_hours": list(DECISION_HOURS) if chain == CHAIN_43 else [0],
            "kappa_bounds": [KAPPA_LOWER, KAPPA_UPPER] if chain == CHAIN_43 else None,
            "forecast_primary": PRIMARY_METHOD,
            "forecast_dual_recent_days": DUAL_RECENT_DAYS,
            "forecast_fallback_constant_price": FALLBACK_CONSTANT_PRICE,
            "delivery_start_index": D_REQ_START,
            "commit_block_periods": COMMIT_BLOCK if chain == CHAIN_43 else PERIODS_PER_DAY,
        },
        "layer_inputs": layer_inputs,
        "forecast_fallbacks": fallback_records,
        "code_sha256": code_fingerprint(code_dir),
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
    }

    write_json(
        output_dir / "solver_status.json",
        {
            "status": 0,
            "message": "all layers optimal",
            "solver": "highs",
            "chain": chain,
            "model": args.model,
            "objective_yuan": metrics["objective_yuan"],
            "delivery_cost_yuan": metrics["delivery"]["cost_total_yuan"],
            "feasible_incumbent": True,
            "mip_gap": None,
            "device": "cpu",
            "gpu_required": False,
            "seed": None,
            "days": days,
            "probe_mode": probe_mode,
            "lp_calls": len(result.layer_records),
            "lp_solver_invocations_nominal": matrix_scale["lp_solver_invocations_nominal"],
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
            "layer_bound_violation_max": max(
                (item.bound_violation_max for item in result.layer_records), default=0.0
            ),
            "layer_seconds_total": float(np.sum([item.seconds for item in result.layer_records]))
            if result.layer_records else 0.0,
            "wall_seconds": elapsed,
            "deterministic": True,
        },
    )
    write_json(
        output_dir / "solution.json",
        {
            "chain": chain,
            "model": args.model,
            "probe_mode": probe_mode,
            "days": days,
            "objective_yuan": metrics["objective_yuan"],
            "cost_plan_yuan": metrics["cost_plan_yuan"],
            "cost_adj_yuan": metrics["cost_adj_yuan"],
            "cost_em_yuan": metrics["cost_em_yuan"],
            "belief": metrics["belief"],
            "delivery": metrics["delivery"],
            "totals": metrics["totals"],
            "identities": metrics["identities"],
            "bounds": metrics["bounds"],
            "statistics": metrics["statistics"],
            "daily": metrics["daily"],
            "checks": metrics["checks"],
            "checks_failed": metrics["checks_failed"],
            "t7_tiebreak": metrics["t7_tiebreak"],
            "forecast_fallbacks": fallback_records + list(result.fallback_records),
            "layer_summary": [item.as_dict() for item in result.layer_records],
            "series": metrics["series"],
        },
    )
    write_json(output_dir / "tables.json", tables)
    write_json(output_dir / "forecast_backtest.json", backtest)
    write_json(output_dir / "tiebreak_audit.json", tiebreak_audit)
    write_json(
        output_dir / "run_manifest.json",
        {
            **run_meta,
            "outcome": "hard_check_failed" if failed else "completed",
            "matrix_scale": matrix_scale,
            "lp_calls": len(result.layer_records),
            "lp_solver_invocations_nominal": matrix_scale["lp_solver_invocations_nominal"],
            "t7_tiebreak": metrics["t7_tiebreak"],
            "tiebreak_artifact": "tiebreak_audit.json",
            "wall_seconds": elapsed,
            "workbook": workbook_name,
            "workbook_info": workbook_info,
            "format_residuals": (workbook_info or {}).get("format_residuals", []),
            "delivery_days": len(delivery_dates_list),
            "delivery": metrics["delivery"],
            "statistics": metrics["statistics"],
            "total_plan_kwh": metrics["delivery"]["total_plan_kwh"],
            "total_purchase_kwh": metrics["delivery"]["total_purchase_kwh"],
            "total_q_em_kwh": metrics["delivery"]["total_q_em_kwh"],
            "total_charge_kwh": metrics["delivery"]["total_charge_kwh"],
            "total_discharge_kwh": metrics["delivery"]["total_discharge_kwh"],
            "total_spill_kwh": metrics["delivery"]["total_spill_kwh"],
            "storage_final_kwh": metrics["totals"]["storage_final_kwh"],
            "checks_failed": failed,
        },
    )

    if probe_mode:
        print(
            "[prob04] **探针模式**（--days < 365）：不写 result{0}.xlsx，改写 probe_result{0}.xlsx；"
            "已跳过「解析界/量级带」四项硬检查；本产物**不是**交付结果。".format(chain)
        )
    print(
        f"[prob04] 链 {chain}（model={args.model}）运行完成：days={days} periods={days * PERIODS_PER_DAY} "
        f"LP={len(result.layer_records)}（名义调用 {matrix_scale['lp_solver_invocations_nominal']}）"
    )
    print(
        f"[prob04] D_full 口径：C_total^act={metrics['objective_yuan']:.4f} 元 "
        f"(C_plan={metrics['cost_plan_yuan']:.4f}, C_adj={metrics['cost_adj_yuan']:.4f}, "
        f"C_em={metrics['cost_em_yuan']:.4f})；Σb={metrics['totals']['total_plan_kwh']:.4f} kWh，"
        f"Σq={metrics['totals']['total_purchase_kwh']:.4f} kWh，Σq^em={metrics['totals']['total_q_em_kwh']:.6f} kWh，"
        f"Σs'={metrics['totals']['total_spill_kwh']:.4f} kWh，Σc={metrics['totals']['total_charge_kwh']:.4f} kWh，"
        f"Σq_dis={metrics['totals']['total_discharge_kwh']:.4f} kWh，"
        f"E_0={metrics['totals']['storage_initial_kwh']:.4f} → E_T={metrics['totals']['storage_final_kwh']:.4f} kWh"
    )
    print(
        f"[prob04] D_req 口径（交付期 {metrics['delivery']['days']} 天）："
        f"C_total^act={metrics['delivery']['cost_total_yuan']:.4f} 元"
        f"（C_plan={metrics['delivery']['cost_plan_yuan']:.4f}, "
        f"C_adj={metrics['delivery']['cost_adj_yuan']:.4f}, "
        f"C_em={metrics['delivery']['cost_em_yuan']:.4f}）；"
        f"C_total^fc={metrics['delivery']['cost_total_fc_yuan']:.4f} 元；"
        f"ΔC_price={metrics['delivery']['delta_c_price_yuan']:.4f} 元"
    )
    print(
        f"[prob04] 恒等式残差：I1={metrics['identities']['I1_daily_max_abs']:.3e}，"
        f"I2={metrics['identities']['I2_daily_max_abs']:.3e}，"
        f"跨日={metrics['identities']['continuity_residual_max']:.3e}，"
        f"状态转移={metrics['identities']['transition_residual_max']:.3e}，"
        f"结算平衡={metrics['identities']['settlement_residual_max']:.3e}，"
        f"层内余额上界={metrics['identities']['layer_spill_upper_violation']:.3e}"
    )
    print(
        f"[prob04] AS21 tie-break：主目标最大相对变化={metrics['t7_tiebreak']['max_primary_relative_change']:.3e}"
        f"（阈值 {T7_INVARIANCE_TOL:.0e}，全部通过={metrics['t7_tiebreak']['all_layers_invariance_passed']}），"
        f"吞吐量 {metrics['t7_tiebreak']['throughput_primary_only_kwh']:.4f}→"
        f"{metrics['t7_tiebreak']['throughput_tiebreak_kwh']:.4f} kWh，"
        f"退化层数={metrics['t7_tiebreak']['degenerate_layers']}/"
        f"{metrics['t7_tiebreak']['layers']}，待提交解来源={metrics['t7_tiebreak']['lexicographic_committed_layers']} "
        f"lexicographic / {metrics['t7_tiebreak']['fallback_committed_layers']} fallback"
    )
    if probe_mode:
        print(
            "[prob04] 探针诊断（**跳过硬检查**，诊断值仅供参考，不构成交付证据）："
            f"交付期 C_total^act={metrics['delivery']['cost_total_yuan']} 元"
            f"（量级带内={metrics['bounds'].get('magnitude_band_delivery_ok')}），"
            f"日均={metrics['bounds'].get('mean_daily_delivery_cost_yuan')} 元"
            f"（量级带内={metrics['bounds'].get('magnitude_band_daily_ok')}），"
            f"解析下界={metrics['bounds'].get('delivery_plan_lower_bound_yuan')} 元，"
            f"构造上界={metrics['bounds'].get('delivery_constructed_upper_bound_yuan')} 元；"
            f"正式量级带 = 交付期 {DELIVERY_MAGNITUDE_BAND_YUAN} 元 / 日均 {DAILY_MAGNITUDE_BAND_YUAN} 元"
        )
    print(
        "[prob04] 预测器回测（D_req 334 天，主判据 MAE）："
        + "；".join(
            f"{name} MAE={backtest['windows']['D_req']['metrics'][name]['mae']:.6f} "
            f"MAPE={backtest['windows']['D_req']['metrics'][name]['mape']:.4%} "
            f"夺冠={int(backtest['windows']['D_req']['metrics'][name]['daily_mae_win_days'])}"
            for name in ALL_METHODS
        )
        + f" ⇒ 选定 {backtest['selection']['selected']}"
    )
    print(f"[prob04] 输出目录：{output_dir}；工作簿={workbook_name}；失败检查={failed}")
    if failed:
        print(f"[prob04] 硬检查未通过：{failed}", file=sys.stderr)
        return EXIT_HARD_CHECK_FAILED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
