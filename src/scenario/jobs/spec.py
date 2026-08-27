"""Serializable job specification for single simulation runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunSpec:
    """Everything needed to execute one simulation run."""

    scenario: str
    overrides: Optional[Dict[str, Any]] = None
    output_dir: Optional[Path] = None
    run_id: Optional[str] = None
    results_root: Optional[Path] = None
    recreate_output: bool = True
    seed: Optional[int] = None
    apply_proposals_path: Optional[Path] = None
    # When set, applied in order after (or instead of) the single path.
    apply_proposals_paths: Optional[List[Path]] = None
    # Prior loop digests for post-run designers (see jobs.design_history).
    design_history: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key in ("output_dir", "results_root", "apply_proposals_path"):
            value = payload.get(key)
            if value is not None:
                payload[key] = str(value)
        paths = payload.get("apply_proposals_paths")
        if paths is not None:
            payload["apply_proposals_paths"] = [str(p) for p in paths]
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RunSpec":
        data = dict(payload)
        for key in ("output_dir", "results_root", "apply_proposals_path"):
            if data.get(key) is not None:
                data[key] = Path(data[key])
        if data.get("apply_proposals_paths") is not None:
            data["apply_proposals_paths"] = [Path(p) for p in data["apply_proposals_paths"]]
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "RunSpec":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def read_json(cls, path: Path) -> "RunSpec":
        return cls.from_json(path.read_text(encoding="utf-8"))


@dataclass
class RunResult:
    """Outcome of a single simulation run."""

    run_dir: Path
    summary: Dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0
    exit_code: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "summary": self.summary,
            "duration_s": round(self.duration_s, 3),
            "exit_code": self.exit_code,
            "error": self.error,
        }
