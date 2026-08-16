"""Deliberation round is a simultaneous (parallel) LLM batch."""

from __future__ import annotations

import json
import threading
import time

from core.agents.types import AgentObservation
from core.llm.base import LLMClient
from environment.protocol import HealthMetrics, HealthStatus, TelemetrySnapshot
from scenario.agents.scrubber_degradation_team import ScrubberDegradationTeam

_TEAM_COUNT = 8


def _obs(step: int = 1) -> AgentObservation:
    return AgentObservation(
        step=step,
        telemetry=TelemetrySnapshot(
            step=step,
            co2_ppm=1100.0,
            scrubber_efficiency=0.8,
            power_margin_w=10.0,
            fan_speed=0.9,
            bypass_enabled=False,
            load_reduced=False,
            anomaly_flags=["scrubber_degradation"],
            eps_support_w=0.0,
            eps_support_steps_remaining=0,
        ),
        health=HealthMetrics(
            step=step,
            co2_status=HealthStatus.WARNING,
            power_status=HealthStatus.SAFE,
            overall=HealthStatus.WARNING,
        ),
    )


def test_llm_deliberation_round_runs_in_parallel(monkeypatch):
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()
    prompts: list[str] = []

    class SlowClient(LLMClient):
        def __init__(self) -> None:
            super().__init__(max_concurrency=_TEAM_COUNT)

        def generate(self, prompt: str) -> str:
            nonlocal in_flight, max_in_flight
            with lock:
                prompts.append(prompt)
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
            if "phase: action" in prompt.lower():
                return json.dumps(
                    {"message": "hold", "reasoning": "test", "commands": []}
                )
            return json.dumps(
                {"message": "SAME_STEP_MARKER watching CO2", "reasoning": "test"}
            )

        def check_connection(self) -> bool:
            return True

    monkeypatch.setattr(
        ScrubberDegradationTeam,
        "_build_llm_client",
        staticmethod(lambda _: SlowClient()),
    )
    team = ScrubberDegradationTeam(
        {
            "mode": "llm",
            "team": {"count": _TEAM_COUNT, "id_prefix": "engineer"},
            "llm": {},
        }
    )
    outcome = team._run_step_llm(_obs())

    delib = [m for m in outcome.messages if m.metadata.get("deliberation_phase") == "deliberation"]
    assert len(delib) == _TEAM_COUNT
    assert max_in_flight == _TEAM_COUNT

    delib_prompts = [p for p in prompts if "phase: deliberation" in p.lower()]
    assert len(delib_prompts) == _TEAM_COUNT
    # Simultaneous round: nobody sees this step's comments while generating.
    assert all("SAME_STEP_MARKER" not in p for p in delib_prompts)


def test_llm_deliberation_survives_second_asyncio_run(monkeypatch):
    """Regression: each step calls asyncio.run(); the client must outlive that."""

    class InstantClient(LLMClient):
        def __init__(self) -> None:
            super().__init__(max_concurrency=4)

        def generate(self, prompt: str) -> str:
            if "phase: action" in prompt.lower():
                return json.dumps({"message": "hold", "reasoning": "test", "commands": []})
            return json.dumps({"message": "watching", "reasoning": "test"})

        def check_connection(self) -> bool:
            return True

    monkeypatch.setattr(
        ScrubberDegradationTeam,
        "_build_llm_client",
        staticmethod(lambda _: InstantClient()),
    )
    team = ScrubberDegradationTeam(
        {
            "mode": "llm",
            "team": {"count": 4, "id_prefix": "engineer"},
            "llm": {},
        }
    )
    first = team._run_step_llm(_obs(1))
    second = team._run_step_llm(_obs(2))
    assert len(first.messages) >= 4
    assert len(second.messages) >= 4
