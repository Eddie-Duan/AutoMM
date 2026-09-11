# ruff: noqa: E501 —— 中文说明长字符串，折行会损害可读性，故按文件豁免行长规则。
"""prob04 ablation 阶段级派生汇总：从 run003 落盘产物装配 `ablations/summary.json`。

- 本脚本**只读** run003 的 `comparison.json` / `criteria.json` / `baseline_check.json` /
  `solver_status.json` / `run_manifest.json` / `forecast_backtest.json`；
- 不做任何求解、不修改 task 输出目录（`plan_v001` §5 要求的顶层 `summary.json` 未由 task 生成，
  本动作以**阶段级派生文件**补齐并登记为技术债 `AB-D1`）；
- 数值不改写：全部字段原样取自产物，仅增加 `provenance` 与 `derived_notes`。

运行（项目根目录）：
    .venv\\Scripts\\python.exe problems/microgrid_2025/prob04/versions/assumption_v001/ablations/build_stage_summary.py
"""

from __future__ import annotations

import json
from pathlib import Path

ABL_DIR = Path(__file__).resolve().parent
RUN_DIRS = {
    "4-2": ABL_DIR / "results" / "prob04_v001_ablation_4-2_run003",
    "4-3": ABL_DIR / "results" / "prob04_v001_ablation_4-3_run003",
}
ACTION_ID = "act-d9d013c46e6647f5"


def read(directory: Path, name: str) -> dict:
    return json.loads((directory / name).read_text(encoding="utf-8"))


def build_chain(chain: str, directory: Path) -> dict:
    comparison = read(directory, "comparison.json")
    criteria = read(directory, "criteria.json")
    baseline = read(directory, "baseline_check.json")
    solver = read(directory, "solver_status.json")
    manifest = read(directory, "run_manifest.json")
    backtest = read(directory, "forecast_backtest.json")
    gate = criteria["criteria"]
    return {
        "chain": chain,
        "task_id": manifest["task_id"],
        "output_directory": manifest["output_directory"],
        "case_counts": manifest["case_counts"],
        "wall_seconds": manifest["wall_seconds"],
        "solver_status": solver,
        "baseline_check": baseline,
        "criteria_failed": criteria["criteria_failed"],
        "checks_failed": manifest["checks_failed"],
        "criteria": {
            "C2": gate["C2"],
            "C3": gate["C3"],
            "C4": gate["C4"],
            "C6": gate["C6"],
            "C_RH_BOUNDARY": gate["C_RH_BOUNDARY"],
            "C1": gate.get("C1"),
        },
        "cost_table_D_req_yuan": {
            name: {
                "D_req_cost_total_yuan": row.get("D_req_cost_total_yuan"),
                "D_req_delta_vs_base_yuan": row.get("D_req_delta_vs_base_yuan"),
                "D_req_delta_pct": row.get("D_req_delta_pct"),
                "D_full_cost_total_yuan": row.get("D_full_cost_total_yuan"),
                "D_full_delta_pct": row.get("D_full_delta_pct"),
                "D_req_sum_q_em_kwh": row.get("D_req_sum_q_em_kwh"),
                "D_req_delta_c_price_yuan": row.get("D_req_delta_c_price_yuan"),
            }
            for name, row in comparison["table"].items()
        },
        "base_reference": comparison["base_reference"],
        "forecast_backtest_metrics_D_req": {
            method: payload
            for method, payload in backtest["windows"]["D_req"]["metrics"].items()
        },
        "forecast_backtest_selection": backtest["selection"],
        "information_set": manifest["information_set"],
        "code_sha256": manifest["code_sha256"],
        "input_md5": {k: v for k, v in manifest["input"].items() if k.endswith("_md5")},
    }


def main() -> int:
    summary = {
        "problem_id": "microgrid_2025",
        "question_id": "prob04",
        "assumption_version": "assumption_v001",
        "formulation_version": "formulation_v001",
        "stage": "ablation",
        "run_id": "run003",
        "provenance": {
            "derived_by": f"ablation-analyst {ACTION_ID}（同步动作，ablation 收尾）",
            "note": (
                "本文件是**阶段级派生汇总**，不是隔离 task 的产物：plan_v001 §5 要求的顶层 summary.json "
                "未由 ablation_prob04.py 生成（该任务只落盘 baseline_check/criteria/comparison/results/"
                "budget_history/forecast_backtest/solver_status/run_manifest.json 与逐 case summary.json）。"
                "本动作按技术债 AB-D1 在阶段目录补齐，未写入两条链的 task 输出目录。"
            ),
            "sources": [str(p.relative_to(ABL_DIR)) for p in RUN_DIRS.values()],
            "formal_numbers": "以 run003 两个隔离 task 的产物为准；run001/run002 与全部 _probe_* 只作审计对照，不作为对照值",
        },
        "chains": {chain: build_chain(chain, directory) for chain, directory in RUN_DIRS.items()},
        "derived_notes": {
            "gates": "C1/C2/C3 强制闸门两链全部通过；criteria_failed=[]；checks_failed=[]；两链 rc=0、supervised、CPU HiGHS、seed=20260911",
            "main_conclusion_family_dependence": "费用水平不依赖模型族（≤0.28%/0.15%）；「日边界 E_{d,144}=E_min 不跨日携带」依赖「逐日 0:00 决策 + 终端自由」结构，H>=3 后失效",
            "svar_43_degeneracy": "S-VAR(4-3) 因预注册的自由追索使 u±≡0，与 S-VAR(4-2) 逐位同解，其 -19.02% 不得读作对冲收益",
            "svar_rh_counterexample": "S-VAR-RH(4-2,H=3) 期望费用比同窗点预测贵 +2.6959%，按 plan_v001 §2 C5 如实登记反例，只对 12 代表日窗口成立",
            "disclosures": "AB-D1…AB-D13 见 ablations/report.md §8（含 C6 在 4-3 判不通过、ΔC_price 基数歧义、ETA 族残差语义、图件不登记为交付图表等）",
        },
    }
    out = ABL_DIR / "summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[summary] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
