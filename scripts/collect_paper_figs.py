# -*- coding: utf-8 -*-
"""把论文需要的图件复制到 paper/figs 并改名为语义化名称（去内部编号）。"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "problems" / "microgrid_2025"
FIGS = ROOT / "paper" / "figs"

P01 = BASE / "prob01/versions/assumption_v003/figures"
P02 = BASE / "prob02/versions/assumption_v001/figures"
P03 = BASE / "prob03/versions/assumption_v001/figures"
P04 = BASE / "prob04/versions/assumption_v001/figures"
R03 = BASE / "prob03/versions/assumption_v001/robustness/results/prob03_v001_robust_run001/figures"
AB4 = BASE / "prob04/versions/assumption_v001/ablations/figures"

MAP = {
    "prob01_input_profile.png": P01 / "prob01_fig_input_profile_dc7b2e52af.png",
    "prob01_netload_arbitrage.png": P01 / "prob01_fig_netload_arbitrage_d9700035cd.png",
    "prob01_dispatch_profile.png": P01 / "prob01_fig_dispatch_profile_e1b9b885da.png",
    "prob01_soc_trajectory.png": P01 / "prob01_fig_soc_trajectory_8b40330c06.png",
    "prob02_temporal_heatmap.png": P02 / "prob02_fig_temporal_heatmap_2aa0a5f976.png",
    "prob02_year_energy_flow.png": P02 / "prob02_fig_year_energy_flow_ed77b9f928.png",
    "prob02_soc_trajectory.png": P02 / "prob02_fig_soc_trajectory_eb0f77c2a5.png",
    "prob02_spec_dates.png": P02 / "prob02_fig_spec_dates_a8ffbf1f32.png",
    "prob02_b_cap_curve.png": BASE / "prob02/versions/assumption_v001/ablations/figures/prob02_ablation_bcap_paper.png",
    "prob03_forecast_chain.png": P03 / "prob03_fig_forecast_chain_78b78a9c24.png",
    "prob03_plan_adjust_profile.png": P03 / "prob03_fig_plan_adjust_profile_5815df79b4.png",
    "prob03_cost_decomposition.png": P03 / "prob03_fig_cost_decomposition_3c230c19db.png",
    "prob03_soc_trajectory.png": P03 / "prob03_fig_soc_trajectory_ae5b14c70a.png",
    "prob04_price_belief_chain.png": P04 / "prob04_fig_price_belief_chain_0f0c113ea4.png",
    "prob04_forecast_backtest.png": P04 / "prob04_fig_forecast_backtest_33ec6918c7.png",
    "prob04_cost_decomposition.png": P04 / "prob04_fig_cost_decomposition_21e04b722c.png",
    "prob04_adjust_heatmap_2d.png": P04 / "prob04_fig_adjust_heatmap_2d_faadb9f50e.png",
    "prob04_emergency_profile.png": P04 / "prob04_fig_emergency_profile_43_ee87fab821.png",
    "robust_tornado.png": R03 / "robustness_prob03_tornado.png",
    "robust_srh_depth.png": AB4 / "ablation_srh_depth.png",
    "robust_svar.png": AB4 / "ablation_svar_hedge.png",
}


def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    missing = []
    for dst, src in MAP.items():
        if src.exists():
            shutil.copyfile(src, FIGS / dst)
        else:
            missing.append(str(src))
    print("copied", len(MAP) - len(missing), "of", len(MAP))
    for m in missing:
        print("MISSING:", m)
    for p in sorted(FIGS.glob("*.png")):
        print(f"{p.name:34s} {p.stat().st_size / 1024:8.1f} KB")

    print("--- code inventory ---")
    for prob in ("prob01", "prob02", "prob03", "prob04"):
        for py in sorted((BASE / prob).glob("versions/*/code/*.py")):
            n = len(py.read_text(encoding="utf-8").splitlines())
            print(f"{prob}/{py.name:24s} {n:5d} lines")


if __name__ == "__main__":
    main()
