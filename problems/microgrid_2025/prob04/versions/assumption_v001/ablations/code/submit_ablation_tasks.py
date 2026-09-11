"""提交 prob04 ablation 两条链的隔离计算 task（两链分别提交、独立 output_directory）。

**run003 修订说明（ablation-analyst，2026-09-12）**：
  * `run002` 的 4-3 task（`4e3e59706fa0888083ec`）以 `code_runtime/process_exit` 失败：
    `S-RH 窗口 LP 未达最优（day=0, t0=36, H=1, status=2）`——窗口把 `4-3` 的「已提交前缀」
    钉在零向量上，与 `E ≥ 1200` 直接冲突 ⇒ 恒 infeasible。
  * 同批还定位到 4 处实现缺陷（`C3` 比对对象错取 `H = 14`、`C4` 单调方向写反、
    `S-VAR(4-3)` 的 `u⁺/u⁻` 方向与 accepted 相反、`_svar_common_equalities` 缺逐场景行偏移
    导致 S-VAR(4-3) 恒不可行），以及 `C8` 残差证据缺口。
  * 本轮提交的是**修复版**（实现纠错，判据 `C1`–`C9` 与阈值一字未改，见 `plan_v003.md`），
    code_hash 变化 ⇒ 新 task_id；因此必须使用**新的 output_directory**（`_run003`），
    不得覆盖 `run001`/`run002` 的产物（plan.md §6）。
  * 两条链同批重跑，保证同代码修订、同参数、同预算可比。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

def find_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "scripts" / "automm" / "tasks.py").is_file():
            return candidate
    raise SystemExit("project root not found")


ROOT = find_root(Path(__file__).resolve())
sys.path.insert(0, str(ROOT / "scripts"))

from automm.tasks import make_task_spec, submit_task  # noqa: E402

CODE = "problems/microgrid_2025/prob04/versions/assumption_v001/ablations/code/ablation_prob04.py"
PY = ".venv/Scripts/python.exe"
DATA = "data"

CASES = {
    "4-2": {
        "config": "problems/microgrid_2025/prob04/versions/assumption_v001/ablations/code/task_config.yaml",
        "output": "problems/microgrid_2025/prob04/versions/assumption_v001/ablations/results/prob04_v001_ablation_4-2_run003",
        "timeout": 5400,
        "wall": 3000,
    },
    "4-3": {
        "config": "problems/microgrid_2025/prob04/versions/assumption_v001/ablations/code/task_config_4-3.yaml",
        "output": "problems/microgrid_2025/prob04/versions/assumption_v001/ablations/results/prob04_v001_ablation_4-3_run003",
        "timeout": 12600,
        "wall": 10800,
    },
}

out = {}
for chain, spec in CASES.items():
    command = [
        PY,
        CODE,
        "--chain",
        chain,
        "--data1",
        "data/附件1.xlsx",
        "--data2",
        "data/附件2.xlsx",
        "--data3",
        "data/附件3.xlsx",
        "--data4",
        "data/附件4.xlsx",
        "--output",
        spec["output"],
        "--days",
        "365",
        "--time-limit",
        "60",
        "--cases",
        "all",
        "--max-wall-seconds",
        str(spec["wall"]),
    ]
    task = make_task_spec(
        problem_id="microgrid_2025",
        question_id="prob04",
        stage="ablation",
        command=command,
        code_path=CODE,
        config_path=spec["config"],
        input_path=DATA,
        assumption_version="assumption_v001",
        formulation_version="formulation_v001",
        output_directory=spec["output"],
        working_directory=".",
        timeout_seconds=spec["timeout"],
        seed=20260911,
    )
    status = submit_task(task)
    out[chain] = {
        "task_id": task["task_id"],
        "task_dir": f"runtime/tasks/{task['task_id']}",
        "status": status["status"],
        "code_hash": task["code_hash"],
        "config_hash": task["config_hash"],
        "source_config_hash": task["source_config_hash"],
        "input_hash": task["input_hash"],
        "output_directory": spec["output"],
        "timeout_seconds": spec["timeout"],
        "command": command,
    }

print(json.dumps(out, ensure_ascii=False, indent=2))
