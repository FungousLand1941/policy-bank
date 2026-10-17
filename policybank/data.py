"""Loaders for the released dataset in ``data/``."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    env = os.environ.get("POLICYBANK_DATA")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "data"


DATA_DIR = _default_data_dir()


def set_data_dir(path: Path | str) -> None:
    """Point every loader (and the analyses built on them) at another dataset directory."""
    global DATA_DIR
    DATA_DIR = Path(path)


@dataclass(frozen=True)
class Episode:
    """One evaluator rollout: a (task, instance) cell scored with partial credit."""

    task_id: int
    task: str
    instance: int
    policy: str
    q: float
    success: bool
    steps: int = 0
    normalized_time: float = 0.0
    run: str = ""

    @property
    def timed_out(self) -> bool:
        """True when the episode ran to the step cap (1.5x the mean demonstration length)."""
        return not self.success and self.normalized_time <= 0.6670


def _path(name: str, data_dir: Path | None) -> Path:
    p = (data_dir or DATA_DIR) / name
    if not p.exists():
        raise FileNotFoundError(
            f"{p} not found. The dataset lives in the repository's data/ folder: run from a clone "
            "(pip install -e .), pass --data DIR, or set POLICYBANK_DATA.")
    return p


def load_json(name: str, data_dir: Path | None = None):
    return json.loads(_path(name, data_dir).read_text(encoding="utf-8"))


def load_tasks(data_dir: Path | None = None) -> list[dict]:
    return load_json("tasks.json", data_dir)


def load_policies(data_dir: Path | None = None) -> dict[str, dict]:
    return load_json("policies.json", data_dir)


def load_route(data_dir: Path | None = None) -> dict:
    return load_json("route.json", data_dir)


def _episodes(path: Path, **extra) -> list[Episode]:
    out = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out.append(Episode(
                task_id=int(r["task_id"]), task=r["task"], instance=int(r["instance"]),
                policy=r["policy"], q=float(r["q"]), success=r["success"] == "1",
                steps=int(r["steps"]), normalized_time=float(r["normalized_time"]),
                run=r.get("run", ""), **extra,
            ))
    return out


def load_official(data_dir: Path | None = None) -> list[Episode]:
    """The 1,000 canonical reported episodes (instances 301-310)."""
    return _episodes(_path("official_episodes.csv", data_dir))


def load_dev(data_dir: Path | None = None, *, selection_only: bool = False) -> list[Episode]:
    """Development rollouts (instances 311-320).

    With ``selection_only`` the rows are restricted to the ones the frozen selection could use:
    development instances, default robot configuration, no evaluation-time variant, and a
    routable policy label.
    """
    path = _path("dev_rollouts.csv", data_dir)
    if not selection_only:
        return _episodes(path)
    keep = []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if r["dev_split"] != "1" or r["variant"] == "1" or r["nondefault_config"] == "1":
            continue
        if r["policy"] in ("unlabelled", "pt50-sweep", "ft-sweep"):
            continue
        keep.append(r)
    return [Episode(task_id=int(r["task_id"]), task=r["task"], instance=int(r["instance"]),
                    policy=r["policy"], q=float(r["q"]), success=r["success"] == "1",
                    steps=int(r["steps"]), normalized_time=float(r["normalized_time"]), run=r["run"])
            for r in keep]
