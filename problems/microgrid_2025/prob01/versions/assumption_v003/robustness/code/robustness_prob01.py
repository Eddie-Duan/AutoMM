# -*- coding: utf-8 -*-
"""prob01 鲁棒性/敏感性实验（隔离 task 入口）。

实验设计见同版本 ``robustness/plan.md``（预注册，先于本代码运行写定）。
本脚本只读 ``data/``（经 ``--input``）与 accepted 产物，向 ``--output`` 写：

- ``solver_status.json``  求解器与可行解标记（供 task_worker 判定 feasible_incumbent）
- ``baseline_check.json`` accepted 基线复现闸门结果（与 run002 逐项对比）
- ``raw_samples.jsonl``   每个情景/随机样本一行的原始指标
- ``summary.json``        分族统计、置信区间、稳定性判据 S1–S6 判定
- ``sensitivity.json``    OAT 弹性与 ±20% 龙卷风数据
- ``figures/*.png``       敏感性图
- ``run_manifest.json``   追踪信息（task_id、代码 sha256、输入 md5、种子、计数、耗时）

模型口径与 accepted 版本一致：``min Σ p_t·b_t``（不带 Δt）、``E_t=E_{t-1}+ηc_t−q_t/η``、
口径丙 ``c_t≤P_max·Δt``、``q_t≤P_max·Δt·η_dis``、``E_0=E_144=E_init``；团队勘误 E1–E3 遵循。
本脚本不修改任何原始数据与上游产物。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linprog

HERE = Path(__file__).resolve()
VERSION_DIR = HERE.parents[2]                       # .../assumption_v003
ACCEPTED_CODE = VERSION_DIR / "code"
RUN002_DIR = VERSION_DIR / "results" / "prob01_v003_f001_run002"
ROOT = HERE.parents[7]
if str(ACCEPTED_CODE) not in sys.path:
    sys.path.insert(0, str(ACCEPTED_CODE))

from prob01_io import read_attachment1, write_json  # noqa: E402

DT = 1.0 / 6.0
TOL = 1e-6
BASE = {
    "eta_ch": 0.9,
    "eta_dis": 0.9,
    "e_init": 6000.0,
    "e_min": 1200.0,
    "e_max": 10800.0,
    "p_max": 5000.0,
    "decay": 1.0,
    "buy_cap_kwh": None,
    "sell_price": 0.0,
    "throughput_cost": 0.0,
    "ac_side": True,
    "dc_side": True,
}
SEED = 20260910

# --------------------------------------------------------------------------- #
# 参数与模型
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Params:
    """单次实验的全部结构参数（默认值 = accepted 基线）。"""

    label: str
    family: str
    eta_ch: float = BASE["eta_ch"]
    eta_dis: float = BASE["eta_dis"]
    e_init: float = BASE["e_init"]
    e_min: float = BASE["e_min"]
    e_max: float = BASE["e_max"]
    p_max: float = BASE["p_max"]
    decay: float = BASE["decay"]                      # 每时段保留率
    buy_cap_kwh: float | None = BASE["buy_cap_kwh"]
    sell_price: float = BASE["sell_price"]            # 元/kWh（s_t 收益，情景）
    throughput_cost: float = BASE["throughput_cost"]  # 元/kWh（c+q，折旧情景）
    ac_side: bool = True                              # 并网点侧功率约束
    dc_side: bool = True                              # 电池侧功率约束
    solver_method: str = "highs"
    presolve: bool = True
    note: str = ""

    @property
    def c_cap(self) -> float:
        caps = []
        if self.ac_side:
            caps.append(self.p_max * DT)
        if self.dc_side:
            caps.append(self.p_max * DT / self.eta_ch)
        return float(min(caps))

    @property
    def q_cap(self) -> float:
        caps = []
        if self.ac_side:
            caps.append(self.p_max * DT)
        if self.dc_side:
            caps.append(self.p_max * DT * self.eta_dis)
        return float(min(caps))


@dataclass
class Case:
    params: Params
    n: int
    price: np.ndarray
    load_kw: np.ndarray
    pv_kw: np.ndarray
    noise: dict[str, Any] = field(default_factory=dict)


def solve_case(case: Case) -> dict[str, Any]:
    """构造并求解单个情景的 LP，返回指标与残差（不抛异常，失败即记录）。"""
    p = case.params
    price = np.asarray(case.price, dtype=float)
    load_energy = np.asarray(case.load_kw, dtype=float) * DT
    pv_energy = np.asarray(case.pv_kw, dtype=float) * DT
    n = case.n
    size = 5 * n
    idx = lambda kind, t: ("b", "c", "q", "s", "E").index(kind) * n + t  # noqa: E731

    objective = np.zeros(size)
    for t in range(n):
        objective[idx("b", t)] = price[t]
        objective[idx("c", t)] = p.throughput_cost
        objective[idx("q", t)] = p.throughput_cost
        objective[idx("s", t)] = -p.sell_price

    a_eq = np.zeros((2 * n, size))
    b_eq = np.zeros(2 * n)
    for t in range(n):                                   # (R1) 电量平衡
        a_eq[t, idx("b", t)] = 1.0
        a_eq[t, idx("q", t)] = 1.0
        a_eq[t, idx("c", t)] = -1.0
        a_eq[t, idx("s", t)] = -1.0
        b_eq[t] = load_energy[t] - pv_energy[t]
    for t in range(n):                                   # (R2) SOC 动态
        row = n + t
        a_eq[row, idx("E", t)] = 1.0
        if t > 0:
            a_eq[row, idx("E", t - 1)] = -p.decay
        a_eq[row, idx("c", t)] = -p.eta_ch
        a_eq[row, idx("q", t)] = 1.0 / p.eta_dis
        b_eq[row] = p.decay * p.e_init if t == 0 else 0.0

    bounds: list[tuple[float, float | None]] = []
    for kind in ("b", "c", "q", "s", "E"):
        for t in range(n):
            if kind == "b":
                bounds.append((0.0, p.buy_cap_kwh))
            elif kind == "c":
                bounds.append((0.0, p.c_cap))
            elif kind == "q":
                bounds.append((0.0, p.q_cap))
            elif kind == "s":
                bounds.append((0.0, float(pv_energy[t])))
            else:
                bounds.append((p.e_init, p.e_init) if t == n - 1 else (p.e_min, p.e_max))

    started = time.perf_counter()
    result = linprog(
        objective,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method=p.solver_method,
        options={"time_limit": 60.0, "presolve": p.presolve},
    )
    elapsed = time.perf_counter() - started

    record: dict[str, Any] = {
        "label": p.label,
        "family": p.family,
        "params": {
            key: value
            for key, value in asdict(p).items()
            if key not in {"label", "family", "solver_method", "presolve", "note"}
        },
        "note": p.note,
        "solver_method": p.solver_method,
        "status": int(result.status),
        "message": str(result.message),
        "iterations": int(result.nit) if result.nit is not None else None,
        "seconds": round(elapsed, 4),
        "c_cap_kwh": round(p.c_cap, 6),
        "q_cap_kwh": round(p.q_cap, 6),
        "no_storage_cost_yuan": round(float(np.sum(price * np.maximum(load_energy - pv_energy, 0.0))), 6),
    }
    if case.noise:
        record["noise"] = case.noise
    if result.x is None:
        record.update(
            {
                "feasible": False,
                "objective_yuan": None,
                "checks_failed": ["no_solution"],
                "equality_residual_max": None,
                "bound_violation_max": None,
            }
        )
        return record

    x = np.asarray(result.x, dtype=float)
    purchase = x[0:n]
    charge = x[n : 2 * n]
    discharge = x[2 * n : 3 * n]
    spill = x[3 * n : 4 * n]
    storage = x[4 * n : 5 * n]

    equality_residual = float(np.max(np.abs(a_eq @ x - b_eq)))
    lower = np.array([item[0] for item in bounds], dtype=float)
    upper = np.array([np.inf if item[1] is None else item[1] for item in bounds], dtype=float)
    bound_violation = float(max(np.max(lower - x), np.max(x - upper)))

    total_purchase = float(np.sum(purchase))
    total_charge = float(np.sum(charge))
    total_discharge = float(np.sum(discharge))
    total_spill = float(np.sum(spill))
    purchase_cost = float(np.sum(price * purchase))
    objective_value = float(result.fun)
    used_range = max(p.e_max - p.e_min, 1e-9)

    side_powers = [
        float(np.max(charge / DT)),
        float(np.max(p.eta_ch * charge / DT)),
        float(np.max(discharge / DT)),
        float(np.max(discharge / (p.eta_dis * DT))),
    ]
    max_side_power = max(side_powers)

    checks = {
        "equality_residual": equality_residual <= TOL,
        "bound_violation": bound_violation <= TOL,
        "periodic_endpoint": abs(float(storage[-1]) - p.e_init) <= TOL,
        "storage_upper": float(np.max(storage)) <= p.e_max + TOL,
        "storage_lower": float(np.min(storage)) >= p.e_min - TOL,
        "charge_cap": float(np.max(charge)) <= p.c_cap + TOL,
        "discharge_cap": float(np.max(discharge)) <= p.q_cap + TOL,
        "spill_bound": bool(np.all(spill <= pv_energy + TOL)),
        "purchase_nonneg": float(np.min(purchase)) >= -TOL,
    }
    identity_i1 = total_discharge - p.eta_ch * p.eta_dis * total_charge
    identity_i2 = total_purchase - float(np.sum(load_energy - pv_energy)) - total_spill - (
        1.0 - p.eta_ch * p.eta_dis
    ) * total_charge
    if abs(p.decay - 1.0) <= 1e-12:
        checks["identity_I1"] = abs(identity_i1) <= 1e-6
        checks["identity_I2"] = abs(identity_i2) <= 1e-6

    record.update(
        {
            "feasible": bool(result.status == 0 and all(checks.values())),
            "objective_yuan": round(objective_value, 6),
            "purchase_cost_yuan": round(purchase_cost, 6),
            "total_purchase_kwh": round(total_purchase, 6),
            "total_charge_kwh": round(total_charge, 6),
            "total_discharge_kwh": round(total_discharge, 6),
            "total_spill_kwh": round(total_spill, 6),
            "storage_min_kwh": round(float(np.min(storage)), 6),
            "storage_max_kwh": round(float(np.max(storage)), 6),
            "storage_final_kwh": round(float(storage[-1]), 6),
            "throughput_kwh": round(total_charge + total_discharge, 6),
            "equivalent_full_cycles": round(total_discharge / used_range, 6),
            "max_side_power_kw": round(max_side_power, 6),
            "simultaneous_periods": int(np.sum((charge > TOL) & (discharge > TOL))),
            "identity_I1_residual": float(identity_i1),
            "identity_I2_residual": float(identity_i2),
            "equality_residual_max": equality_residual,
            "bound_violation_max": bound_violation,
            "checks_failed": [name for name, ok in checks.items() if not ok],
        }
    )
    record["arbitrage_gain_yuan"] = round(record["no_storage_cost_yuan"] - objective_value, 6)
    record["arbitrage_gain_ratio"] = round(
        (record["no_storage_cost_yuan"] - objective_value) / record["no_storage_cost_yuan"], 6
    )
    return record


# --------------------------------------------------------------------------- #
# 情景矩阵
# --------------------------------------------------------------------------- #


def build_matrix(data, families: set[str]) -> list[Case]:
    price, load, pv = data.price, data.load_kw, data.pv_kw
    n = data.periods

    def case(params: Params, **arrays) -> Case:
        return Case(
            params=params,
            n=n,
            price=arrays.get("price", price),
            load_kw=arrays.get("load_kw", load),
            pv_kw=arrays.get("pv_kw", pv),
        )

    matrix: list[Case] = []
    if "baseline" in families:
        matrix.append(case(Params(label="baseline", family="baseline", note="accepted 口径，run002 复现闸门")))

    if "eta" in families:
        for eta in (0.80, 0.85, 0.90, 0.95, 1.00):
            matrix.append(
                case(Params(label=f"eta_{eta:.2f}", family="eta", eta_ch=eta, eta_dis=eta, note="两侧同效率"))
            )
    if "init" in families:
        for value in (3000.0, 4500.0, 6000.0, 7500.0, 9000.0):
            matrix.append(
                case(Params(label=f"init_{int(value)}", family="init", e_init=value, note="E_0=E_144=E_init"))
            )
    if "pmax" in families:
        for value in (4000.0, 5000.0, 6000.0):
            matrix.append(case(Params(label=f"pmax_{int(value)}", family="pmax", p_max=value, note="口径丙同步换算")))
    if "emin" in families:
        for value in (600.0, 1200.0, 2400.0):
            matrix.append(case(Params(label=f"emin_{int(value)}", family="emin", e_min=value, note="E_max=10800")))
    if "emax" in families:
        for value in (9600.0, 10800.0):
            matrix.append(case(Params(label=f"emax_{int(value)}", family="emax", e_max=value, note="E_min=1200")))
    if "d10" in families:
        matrix.append(case(Params(label="d10_jia", family="d10", ac_side=True, dc_side=False, note="甲：并网点侧")))
        matrix.append(case(Params(label="d10_yi", family="d10", ac_side=False, dc_side=True, note="乙：电池侧")))
        matrix.append(
            case(Params(label="d10_bing", family="d10", ac_side=True, dc_side=True, note="丙：交集（accepted）"))
        )
    if "eta_placement" in families:
        s = float(np.sqrt(0.9))
        matrix.append(
            case(Params(label="place_both", family="eta_placement", eta_ch=0.9, eta_dis=0.9, note="两侧各 0.9"))
        )
        matrix.append(
            case(
                Params(
                    label="place_charge_only",
                    family="eta_placement",
                    eta_ch=0.9,
                    eta_dis=1.0,
                    note="仅充电侧 0.9",
                )
            )
        )
        matrix.append(
            case(
                Params(
                    label="place_discharge_only",
                    family="eta_placement",
                    eta_ch=1.0,
                    eta_dis=0.9,
                    note="仅放电侧 0.9",
                )
            )
        )
        matrix.append(
            case(Params(label="place_round_trip", family="eta_placement", eta_ch=s, eta_dis=s, note="往返整体 0.9"))
        )
    if "depreciation" in families:
        for value in (0.0, 0.05, 0.10, 0.20, 0.50):
            matrix.append(
                case(
                    Params(
                        label=f"deg_{value:.2f}",
                        family="depreciation",
                        throughput_cost=value,
                        note="单位吞吐成本（元/kWh，作用 c+q）",
                    )
                )
            )
    if "self_discharge" in families:
        for rho in (0.0, 0.001, 0.005, 0.01):
            matrix.append(
                case(
                    Params(
                        label=f"decay_{rho:.3f}",
                        family="self_discharge",
                        decay=1.0 - rho * DT,
                        note=f"自放电率 {rho}/h",
                    )
                )
            )
    if "buy_cap" in families:
        for kw in (3000.0, 4000.0, 5000.0, 6000.0):
            matrix.append(
                case(
                    Params(
                        label=f"buycap_{int(kw)}",
                        family="buy_cap",
                        buy_cap_kwh=kw * DT,
                        note="并网点购电功率上限",
                    )
                )
            )
    if "sell_price" in families:
        for value in (0.0, 0.10, 0.20, 0.35, 0.50):
            matrix.append(
                case(
                    Params(
                        label=f"sell_{value:.2f}",
                        family="sell_price",
                        sell_price=value,
                        note="余电/弃光上网价（题面未给，仅情景）",
                    )
                )
            )
    if "solver" in families:
        for method, presolve, tag in (
            ("highs", True, "highs"),
            ("highs-ds", True, "highs-ds"),
            ("highs-ipm", True, "highs-ipm"),
            ("highs", False, "highs_nopresolve"),
        ):
            matrix.append(
                case(
                    Params(
                        label=f"solver_{tag}",
                        family="solver",
                        solver_method=method,
                        presolve=presolve,
                        note="求解器/预求解对比",
                    )
                )
            )
    return matrix


def build_noise(data, samples: int, seed: int) -> list[Case]:
    """乘性预测噪声：联合（价+载+光）与单源。"""
    rng = np.random.default_rng(seed)
    price, load, pv = data.price, data.load_kw, data.pv_kw
    n = data.periods
    cases: list[Case] = []

    def factors(sigma: float) -> np.ndarray:
        return np.maximum(0.02, 1.0 + sigma * rng.standard_normal(n))

    plan = [
        ("joint", (0.05, 0.10, 0.20), ("price", "load", "pv")),
        ("price_only", (0.10, 0.20), ("price",)),
        ("load_only", (0.10, 0.20), ("load",)),
        ("pv_only", (0.10, 0.20), ("pv",)),
    ]
    for name, sigmas, sources in plan:
        for sigma in sigmas:
            for index in range(samples):
                fp = factors(sigma) if "price" in sources else np.ones(n)
                fl = factors(sigma) if "load" in sources else np.ones(n)
                fv = factors(sigma) if "pv" in sources else np.ones(n)
                cases.append(
                    Case(
                        params=Params(
                            label=f"noise_{name}_s{int(sigma * 100):02d}_{index:03d}",
                            family=f"noise_{name}",
                            note="乘性预测噪声",
                        ),
                        n=n,
                        price=price * fp,
                        load_kw=load * fl,
                        pv_kw=pv * fv,
                        noise={
                            "source": name,
                            "sigma": sigma,
                            "index": index,
                            "price_factor_mean": round(float(np.mean(fp)), 6),
                            "load_factor_mean": round(float(np.mean(fl)), 6),
                            "pv_factor_mean": round(float(np.mean(fv)), 6),
                        },
                    )
                )
    return cases


# --------------------------------------------------------------------------- #
# 统计与判据
# --------------------------------------------------------------------------- #


def bootstrap_ci(values: np.ndarray, seed: int, resamples: int = 1000) -> list[float]:
    if values.size == 0:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, values.size, size=(resamples, values.size))
    means = values[draws].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def summarize(values: list[float]) -> dict[str, Any]:
    array = np.asarray([v for v in values if v is not None], dtype=float)
    if array.size == 0:
        return {"count": 0}
    return {
        "count": int(array.size),
        "mean": round(float(np.mean(array)), 6),
        "std": round(float(np.std(array, ddof=1)) if array.size > 1 else 0.0, 6),
        "min": round(float(np.min(array)), 6),
        "p2_5": round(float(np.percentile(array, 2.5)), 6),
        "p25": round(float(np.percentile(array, 25)), 6),
        "median": round(float(np.median(array)), 6),
        "p75": round(float(np.percentile(array, 75)), 6),
        "p97_5": round(float(np.percentile(array, 97.5)), 6),
        "max": round(float(np.max(array)), 6),
        "ci95_mean": [round(v, 6) for v in bootstrap_ci(array, SEED)],
    }


def nearest(grid: list[float], value: float) -> float:
    return min(grid, key=lambda item: abs(item - value))


def main() -> int:
    parser = argparse.ArgumentParser(description="prob01 robustness 实验")
    parser.add_argument("--input", default="data/附件1.xlsx")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--samples", type=int, default=100, help="每档噪声样本数")
    parser.add_argument("--families", default="all")
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    data = read_attachment1(Path(args.input), expected_rows=144)
    all_families = {
        "baseline",
        "eta",
        "init",
        "pmax",
        "emin",
        "emax",
        "d10",
        "eta_placement",
        "depreciation",
        "self_discharge",
        "buy_cap",
        "sell_price",
        "solver",
        "noise",
    }
    families = (
        all_families
        if args.families == "all"
        else {item.strip() for item in args.families.split(",") if item.strip()}
    )
    unknown = families - all_families
    if unknown:
        print(f"未知情景族：{sorted(unknown)}", file=sys.stderr)
        return 3

    records: list[dict[str, Any]] = []
    matrix = build_matrix(data, families)
    for case in matrix:
        records.append(solve_case(case))
        print(f"[matrix] {records[-1]['label']} feasible={records[-1]['feasible']}", flush=True)
    noise_records: list[dict[str, Any]] = []
    if "noise" in families:
        noise_cases = build_noise(data, args.samples, args.seed)
        for index, case in enumerate(noise_cases, start=1):
            noise_records.append(solve_case(case))
            if index % 50 == 0:
                print(f"[noise] {index}/{len(noise_cases)}", flush=True)
    records.extend(noise_records)

    with (output / "raw_samples.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")

    # ---------- 基线复现闸门 ----------
    baseline = next((item for item in records if item["label"] == "baseline"), None)
    reference = json.loads((RUN002_DIR / "solution.json").read_text(encoding="utf-8"))
    ref_totals = reference["totals"]
    baseline_check: dict[str, Any] = {
        "reference": "results/prob01_v003_f001_run002/solution.json",
        "reference_sha256": hashlib.sha256((RUN002_DIR / "solution.json").read_bytes()).hexdigest(),
        "compared": {},
        "passed": False,
    }
    if baseline is None or not baseline.get("feasible"):
        baseline_check["error"] = "baseline 未运行或不可行"
    else:
        pairs = {
            "objective_yuan": (baseline["objective_yuan"], reference["objective_yuan"]),
            "total_purchase_kwh": (baseline["total_purchase_kwh"], ref_totals["total_purchase_kwh"]),
            "total_charge_kwh": (baseline["total_charge_kwh"], ref_totals["total_charge_kwh"]),
            "total_discharge_kwh": (baseline["total_discharge_kwh"], ref_totals["total_discharge_kwh"]),
            "total_spill_kwh": (baseline["total_spill_kwh"], ref_totals["total_spill_kwh"]),
            "max_side_power_kw": (baseline["max_side_power_kw"], ref_totals["max_side_power_kw"]),
        }
        ok = True
        for name, (got, want) in pairs.items():
            scale = max(abs(want), 1.0)
            relative = abs(got - want) / scale
            entry = {"ours": got, "reference": want, "relative_diff": relative, "passed": relative <= 1e-6}
            baseline_check["compared"][name] = entry
            ok = ok and entry["passed"]
        baseline_check["passed"] = bool(ok)
    write_json(output / "baseline_check.json", baseline_check)
    write_json(
        output / "solver_status.json",
        {
            "solver": "scipy.optimize.linprog",
            "method": "highs",
            "device": "cpu",
            "gpu_required": False,
            "seed": args.seed,
            "baseline_feasible": bool(baseline and baseline.get("feasible")),
            "feasible_incumbent": bool(baseline and baseline.get("feasible")),
            "baseline_check_passed": baseline_check["passed"],
            "cases_total": len(records),
            "cases_infeasible": sum(1 for item in records if not item.get("feasible")),
        },
    )
    if not baseline_check["passed"]:
        write_json(
            output / "run_manifest.json",
            {
                "outcome": "baseline_mismatch",
                "checks_failed": ["baseline_reproduction"],
                "cases_total": len(records),
            },
        )
        print("基线复现失败，整批作废（exit 4）", file=sys.stderr)
        return 4

    # ---------- 分族统计 ----------
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(record["family"], []).append(record)
    summary: dict[str, Any] = {
        "baseline_objective_yuan": baseline["objective_yuan"],
        "baseline_no_storage_cost_yuan": baseline["no_storage_cost_yuan"],
        "families": {},
    }
    for family, items in sorted(groups.items()):
        feasible = [item for item in items if item.get("feasible")]
        objectives = [item["objective_yuan"] for item in feasible]
        deltas = [
            (item["objective_yuan"] - baseline["objective_yuan"]) / baseline["objective_yuan"] for item in feasible
        ]
        summary["families"][family] = {
            "count": len(items),
            "feasible_count": len(feasible),
            "feasible_rate": round(len(feasible) / len(items), 6),
            "objective": summarize(objectives),
            "relative_delta": summarize(deltas),
            "arbitrage_ratio": summarize([item["arbitrage_gain_ratio"] for item in feasible]),
            "checks_failed_union": sorted({name for item in items for name in item.get("checks_failed", [])}),
            "labels": [item["label"] for item in items],
        }

    # ---------- OAT 弹性 ----------
    def oat(family: str, key: str, grid: list[float], x0: float) -> dict[str, Any]:
        items = {round(item["params"][key], 9): item for item in groups.get(family, [])}
        if not items:
            return {}
        base_cost = baseline["objective_yuan"]
        result: dict[str, Any] = {"grid": grid, "cost": {}, "relative_change": {}, "elasticity": {}}
        for value in grid:
            item = items.get(round(value, 9))
            if not item or not item.get("feasible"):
                continue
            delta = (item["objective_yuan"] - base_cost) / base_cost
            result["cost"][str(value)] = item["objective_yuan"]
            result["relative_change"][str(value)] = round(delta, 6)
            if abs(value - x0) > 1e-12:
                result["elasticity"][str(value)] = round(delta / ((value - x0) / x0), 6)
        return result

    sensitivity = {
        "eta": oat("eta", "eta_ch", [0.80, 0.85, 0.90, 0.95, 1.00], 0.9),
        "e_init": oat("init", "e_init", [3000.0, 4500.0, 6000.0, 7500.0, 9000.0], 6000.0),
        "p_max": oat("pmax", "p_max", [4000.0, 5000.0, 6000.0], 5000.0),
        "e_min": oat("emin", "e_min", [600.0, 1200.0, 2400.0], 1200.0),
        "e_max": oat("emax", "e_max", [9600.0, 10800.0], 10800.0),
    }
    tornado = {}
    for name, family, key, grid, x0 in (
        ("eta", "eta", "eta_ch", [0.80, 0.85, 0.90, 0.95, 1.00], 0.9),
        ("e_init", "init", "e_init", [3000.0, 4500.0, 6000.0, 7500.0, 9000.0], 6000.0),
        ("p_max", "pmax", "p_max", [4000.0, 5000.0, 6000.0], 5000.0),
    ):
        low = nearest(grid, x0 * 0.8)
        high = nearest(grid, x0 * 1.2)
        entry = {"low_value": low, "high_value": high}
        for tag, value in (("low", low), ("high", high)):
            item = next(
                (
                    item
                    for item in groups.get(family, [])
                    if abs(item["params"][key] - value) <= 1e-9 and item.get("feasible")
                ),
                None,
            )
            entry[f"{tag}_relative_change"] = (
                round((item["objective_yuan"] - baseline["objective_yuan"]) / baseline["objective_yuan"], 6)
                if item
                else None
            )
        tornado[name] = entry
    sensitivity["tornado_20pct"] = tornado
    write_json(output / "sensitivity.json", sensitivity)

    # ---------- 稳定性判据 S1–S6 ----------
    # 核心族：保持 accepted 目标口径 Σp·b 不放宽（参数/噪声/求解器/自放电），用于 S1/S4 判定。
    # 结构族（depreciation/sell_price/buy_cap）改变目标定义或约束，单列为「情景发现」，不计入 S1/S4，
    # 避免把「有意的结构变化」误判为模型脆弱（见 plan.md §2 与 §3.4）。
    core_families = {"baseline", "eta", "init", "pmax", "emin", "emax", "d10", "eta_placement",
                     "self_discharge", "solver"}
    structural_families = {"depreciation", "sell_price", "buy_cap"}
    noise_families = [name for name in groups if name.startswith("noise_")]
    core_names = [name for name in groups if name in core_families] + noise_families
    joint20 = [
        item
        for item in groups.get("noise_joint", [])
        if item["noise"]["sigma"] == 0.20 and item.get("feasible")
    ]
    joint20_values = np.asarray([item["objective_yuan"] for item in joint20], dtype=float)
    criteria: dict[str, Any] = {}
    core_total = sum(len(groups[name]) for name in core_names)
    core_feasible = sum(1 for name in core_names for item in groups[name] if item.get("feasible"))
    core_rate = core_feasible / max(core_total, 1)
    criteria["S1_core_feasible_rate"] = {"value": round(core_rate, 6), "threshold": 0.95, "passed": core_rate >= 0.95}
    criteria["S1_parameter_family_feasible_rate"] = {
        "value": round(
            sum(1 for name in core_families if name in groups for item in groups[name] if item.get("feasible"))
            / max(sum(len(groups[name]) for name in core_families if name in groups), 1),
            6,
        ),
        "threshold": 0.99,
        "passed": (
            sum(1 for name in core_families if name in groups for item in groups[name] if item.get("feasible"))
            / max(sum(len(groups[name]) for name in core_families if name in groups), 1)
        )
        >= 0.99,
    }
    oat_max = max(
        [
            abs(value)
            for item in sensitivity.values()
            if isinstance(item, dict)
            for value in item.get("relative_change", {}).values()
        ]
        or [0.0]
    )
    criteria["S2_oat_max_abs_relative_change"] = {
        "value": round(oat_max, 6),
        "threshold": 0.25,
        "passed": oat_max <= 0.25,
    }
    if joint20_values.size:
        half_width = float(joint20_values.max() - joint20_values.min()) / 2.0 / baseline["objective_yuan"]
        mean_shift = abs(float(joint20_values.mean()) - baseline["objective_yuan"]) / baseline["objective_yuan"]
        criteria["S3_noise_joint20_half_width"] = {
            "value": round(half_width, 6),
            "threshold": 0.20,
            "passed": half_width <= 0.20,
        }
        criteria["S3_noise_joint20_mean_shift"] = {
            "value": round(mean_shift, 6),
            "threshold": 0.10,
            "passed": mean_shift <= 0.10,
        }
    order_ok = all(
        item["arbitrage_gain_ratio"] > 0 for name in core_names for item in groups[name] if item.get("feasible")
    )
    criteria["S4_order_stability"] = {"value": bool(order_ok), "threshold": True, "passed": bool(order_ok)}
    eta_elast = sensitivity["eta"].get("elasticity", {})
    p_max_elast = sensitivity["p_max"].get("elasticity", {})
    init_elast = sensitivity["e_init"].get("elasticity", {})
    sign_ok = (
        all(value <= 1e-9 for value in eta_elast.values())
        and all(value <= 1e-9 for value in p_max_elast.values())
        and all(abs(value) <= 1.5 for value in init_elast.values())
    )
    criteria["S5_sign_and_elasticity"] = {"value": bool(sign_ok), "threshold": True, "passed": bool(sign_ok)}
    solver_items = [item for item in groups.get("solver", []) if item.get("feasible")]
    if len(solver_items) >= 2:
        objectives = np.asarray([item["objective_yuan"] for item in solver_items], dtype=float)
        spread = float(objectives.max() - objectives.min()) / baseline["objective_yuan"]
        criteria["S6_solver_consistency"] = {"value": round(spread, 12), "threshold": 1e-6, "passed": spread <= 1e-6}
    summary["criteria"] = criteria
    summary["structural_findings"] = {
        family: {
            "feasible_rate": (
                sum(1 for item in groups.get(family, []) if item.get("feasible")) / max(len(groups.get(family, [])), 1)
            ),
            "max_relative_delta": max(
                [
                    (item["objective_yuan"] - baseline["objective_yuan"]) / baseline["objective_yuan"]
                    for item in groups.get(family, [])
                    if item.get("feasible")
                ]
                or [0.0]
            ),
            "min_relative_delta": min(
                [
                    (item["objective_yuan"] - baseline["objective_yuan"]) / baseline["objective_yuan"]
                    for item in groups.get(family, [])
                    if item.get("feasible")
                ]
                or [0.0]
            ),
            "infeasible_labels": [item["label"] for item in groups.get(family, []) if not item.get("feasible")],
            "arbitrage_reversal": [
                item["label"]
                for item in groups.get(family, [])
                if item.get("feasible") and item["arbitrage_gain_ratio"] <= 0
            ],
        }
        for family in sorted(structural_families)
        if family in groups
    }
    failed = [name for name, item in criteria.items() if not item["passed"]]
    summary["stability_grade"] = (
        "稳定" if not failed else "条件稳定" if len(failed) <= 1 else "脆弱（需缩小适用范围）"
    )
    summary["criteria_failed"] = failed
    write_json(output / "summary.json", summary)

    # ---------- 敏感性图 ----------
    figures: list[str] = []
    if not args.no_figures:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
        figure_dir = output / "figures"
        figure_dir.mkdir(parents=True, exist_ok=True)
        base_cost = baseline["objective_yuan"]

        # 图 1 龙卷风图（±20% 网格点）
        names = [name for name in ("eta", "e_init", "p_max") if tornado[name].get("low_relative_change") is not None]
        fig, ax = plt.subplots(figsize=(7, 3.6))
        for index, name in enumerate(names):
            low = tornado[name]["low_relative_change"] * 100
            high = tornado[name]["high_relative_change"] * 100
            ax.barh(index, low, color="#c0504d", alpha=0.85, label="-20%" if index == 0 else None)
            ax.barh(index, high, color="#4f81bd", alpha=0.85, label="+20%" if index == 0 else None)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(
            [f"{name}\n(low={tornado[name]['low_value']}, high={tornado[name]['high_value']})" for name in names]
        )
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_xlabel("relative change of C* (%)")
        ax.set_title("Tornado: OAT parameter perturbation (nearest grid point to ±20%)")
        ax.legend(loc="lower right")
        fig.tight_layout()
        fig.savefig(figure_dir / "robustness_tornado.png")
        plt.close(fig)
        figures.append("robustness_tornado.png")

        # 图 2 响应曲线
        fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
        for ax, (name, family, key) in zip(
            axes,
            (("eta", "eta", "eta_ch"), ("e_init", "init", "e_init"), ("p_max", "pmax", "p_max")),
        ):
            items = sorted(
                [item for item in groups.get(family, []) if item.get("feasible")], key=lambda item: item["params"][key]
            )
            xs = [item["params"][key] for item in items]
            ys = [item["objective_yuan"] for item in items]
            ax.plot(xs, ys, marker="o", color="#4f81bd")
            ax.axhline(base_cost, color="gray", linestyle="--", linewidth=0.9)
            ax.set_xlabel(key)
            ax.set_ylabel("C* (CNY)")
            ax.set_title(f"C* vs {name}")
        fig.tight_layout()
        fig.savefig(figure_dir / "robustness_response_curves.png")
        plt.close(fig)
        figures.append("robustness_response_curves.png")

        # 图 3 噪声 ECDF
        fig, ax = plt.subplots(figsize=(7, 4))
        for sigma, color in ((0.05, "#4f81bd"), (0.10, "#9bbb59"), (0.20, "#c0504d")):
            values = np.sort(
                np.asarray(
                    [
                        item["objective_yuan"]
                        for item in groups.get("noise_joint", [])
                        if item["noise"]["sigma"] == sigma and item.get("feasible")
                    ],
                    dtype=float,
                )
            )
            if values.size:
                ax.step(
                    values,
                    np.arange(1, values.size + 1) / values.size,
                    where="post",
                    color=color,
                    label=f"joint sigma={int(sigma * 100)}%",
                )
        ax.axvline(base_cost, color="black", linestyle=":", label="accepted baseline")
        ax.set_xlabel("C* (CNY)")
        ax.set_ylabel("ECDF")
        ax.set_title("Forecast-noise propagation (100 samples per sigma, joint price/load/PV)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(figure_dir / "robustness_noise_ecdf.png")
        plt.close(fig)
        figures.append("robustness_noise_ecdf.png")

        # 图 4 结构情景柱状
        scenario_labels: list[str] = []
        scenario_deltas: list[float] = []
        for family in ("depreciation", "self_discharge", "buy_cap", "sell_price", "d10", "eta_placement"):
            for item in groups.get(family, []):
                if item.get("feasible"):
                    scenario_labels.append(item["label"])
                    scenario_deltas.append((item["objective_yuan"] - base_cost) / base_cost * 100)
        fig, ax = plt.subplots(figsize=(10, 4.2))
        colors = ["#4f81bd" if value >= 0 else "#9bbb59" for value in scenario_deltas]
        ax.bar(range(len(scenario_labels)), scenario_deltas, color=colors)
        ax.set_xticks(range(len(scenario_labels)))
        ax.set_xticklabels(scenario_labels, rotation=60, ha="right", fontsize=7)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_ylabel("relative change of C* (%)")
        ax.set_title("Structural scenarios vs accepted baseline")
        fig.tight_layout()
        fig.savefig(figure_dir / "robustness_scenarios.png")
        plt.close(fig)
        figures.append("robustness_scenarios.png")

        # 图 5 spider（归一化 OAT 响应）
        fig, ax = plt.subplots(figsize=(6, 4.4))
        for name, family, key in (
            ("eta", "eta", "eta_ch"),
            ("e_init", "init", "e_init"),
            ("p_max", "pmax", "p_max"),
            ("e_min", "emin", "e_min"),
            ("e_max", "emax", "e_max"),
        ):
            items = sorted(
                [item for item in groups.get(family, []) if item.get("feasible")],
                key=lambda item: item["params"][key],
            )
            if not items:
                continue
            xs = np.asarray([item["params"][key] for item in items], dtype=float)
            ys = np.asarray([(item["objective_yuan"] - base_cost) / base_cost for item in items], dtype=float)
            span = max(abs(xs - xs.mean()).max(), 1e-9)
            ax.plot((xs - xs.mean()) / span, ys, marker="o", label=name)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xlabel("normalized parameter deviation")
        ax.set_ylabel("relative change of C*")
        ax.set_title("Spider plot: OAT response (normalized)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(figure_dir / "robustness_spider.png")
        plt.close(fig)
        figures.append("robustness_spider.png")

    # ---------- 追踪 manifest ----------
    code_files = sorted(HERE.parent.glob("*.py"))
    code_sha = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in code_files}
    manifest = {
        "stage": "robustness",
        "question_id": "prob01",
        "assumption_version": "assumption_v003",
        "formulation_version": "formulation_v001",
        "task_id": __import__("os").environ.get("AUTOMM_TASK_ID"),
        "output_directory": str(output.as_posix()),
        "input_md5": data.md5,
        "reference_run002_sha256": baseline_check["reference_sha256"],
        "seed": args.seed,
        "noise_samples_per_setting": args.samples,
        "families": sorted(families),
        "cases_total": len(records),
        "cases_infeasible": sum(1 for item in records if not item.get("feasible")),
        "figures": figures,
        "code_sha256": code_sha,
        "device": "cpu",
        "gpu_required": False,
        "baseline_check": baseline_check["passed"],
        "criteria_failed": failed,
        "checks_failed": ([] if baseline_check["passed"] else ["baseline_reproduction"]) + failed,
        "outcome": "completed" if not failed else "completed_with_findings",
        "wall_clock_seconds": round(time.perf_counter() - started, 3),
        "accepted_code_sha256": {
            "prob01_model.py": hashlib.sha256((ACCEPTED_CODE / "prob01_model.py").read_bytes()).hexdigest(),
            "prob01_io.py": hashlib.sha256((ACCEPTED_CODE / "prob01_io.py").read_bytes()).hexdigest(),
        },
    }
    write_json(output / "run_manifest.json", manifest)
    print(
        json.dumps(
            {"outcome": manifest["outcome"], "cases": len(records), "failed_criteria": failed},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
