"""Loop command — multi-run design→verification orchestrator."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

import typer

from scenario.jobs.loop import (
    DEFAULT_MAX_ACTIONS_PER_STEP,
    DEFAULT_MAX_LOOPS,
    DEFAULT_TARGET_CREW,
    LoopSpec,
    execute_loop,
)
from scenario.runner import scenario_descriptions
from tools.cli import exit_codes
from tools.cli.commands import run as run_cmd
from tools.cli.output import console, print_error

DEFAULT_SCENARIO = "ssos_eclss_loop"
LOOP_ID_ENV_VAR = "EA_LOOP_ID"


def register(app: typer.Typer) -> None:
    app.command("loop")(loop)


def loop(
    scenario: Optional[str] = typer.Argument(
        None,
        help="Scenario name (default: ssos_eclss_loop).",
    ),
    actor_mode: Optional[str] = typer.Option(
        None,
        "--actor-mode",
        help="ssos_eclss_loop actor mode: none, labeled_rule_base, or llm.",
    ),
    design_mode: Optional[str] = typer.Option(
        None,
        "--design-mode",
        help="ssos_eclss_loop design mode: none, labeled_rule_base, or llm.",
    ),
    agents_mode: Optional[str] = typer.Option(
        None,
        "--agents-mode",
        help="Agent mode. On ssos_eclss_loop, alias for --actor-mode.",
    ),
    steps: Optional[int] = typer.Option(None, "--steps", help="Override simulation.steps."),
    backend: Optional[str] = typer.Option(
        None,
        "--backend",
        help="ssos_eclss_loop backend (default for loop: plant_sim).",
    ),
    max_loops: int = typer.Option(
        DEFAULT_MAX_LOOPS,
        "--max-loops",
        help="Maximum design→verify iterations (default 15).",
    ),
    target_crew: int = typer.Option(
        DEFAULT_TARGET_CREW,
        "--target-crew",
        help="Stop when summary.crew_remaining equals this value (default 50).",
    ),
    loop_id: Optional[str] = typer.Option(
        None,
        "--loop-id",
        "--run-id",
        help=(
            "REQUIRED. Prefix for result dirs "
            "(e003loop → e003loop-run01 .. e003loop-run15). "
            "Alias: --run-id. Or set EA_LOOP_ID / --set loop_id=e003loop."
        ),
    ),
    max_actions_per_step: int = typer.Option(
        DEFAULT_MAX_ACTIONS_PER_STEP,
        "--max-actions-per-step",
        help="Initial agents.actor.max_actions_per_step (default 2).",
    ),
    results_root: Optional[Path] = typer.Option(
        None,
        "--results-root",
        help="Override results base directory.",
    ),
    llm_provider: Optional[str] = typer.Option(None, "--llm-provider"),
    llm_model: Optional[str] = typer.Option(None, "--llm-model"),
    inject_failures: Optional[bool] = typer.Option(
        None,
        "--inject-failures/--no-inject-failures",
    ),
    seed: Optional[int] = typer.Option(None, "--seed"),
    set_values: List[str] = typer.Option([], "--set"),
    override_file: Optional[Path] = typer.Option(None, "--override-file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print plan without executing."),
    json_output: bool = typer.Option(False, "--json"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    scenario_name = scenario or DEFAULT_SCENARIO
    known = scenario_descriptions()
    if scenario_name not in known:
        names = ", ".join(sorted(known))
        print_error(
            f"Unknown scenario: {scenario_name!r}.",
            hint=f"Try: ea scenarios\nAvailable: {names}",
        )
        raise typer.Exit(exit_codes.USER_ERROR)

    if max_loops < 1:
        print_error("--max-loops must be >= 1")
        raise typer.Exit(exit_codes.USER_ERROR)
    if target_crew < 1:
        print_error("--target-crew must be >= 1")
        raise typer.Exit(exit_codes.USER_ERROR)
    if max_actions_per_step < 1:
        print_error("--max-actions-per-step must be >= 1")
        raise typer.Exit(exit_codes.USER_ERROR)

    set_loop_id, filtered_sets = _extract_loop_id_from_sets(set_values)

    try:
        overrides = run_cmd._build_overrides(
            scenario_name=scenario_name,
            agents_mode=agents_mode,
            actor_mode=actor_mode,
            design_mode=design_mode,
            steps=steps,
            backend=backend,
            inject_failures=inject_failures,
            llm_provider=llm_provider,
            llm_model=llm_model,
            set_values=filtered_sets,
            override_file=override_file,
        )
        overrides = run_cmd._apply_cli_defaults(scenario_name, overrides)
        overrides = run_cmd._apply_llm_cli_to_llm_sides(
            scenario_name, overrides, llm_provider=llm_provider, llm_model=llm_model
        )
        overrides = run_cmd._materialize_resolved_llm(scenario_name, overrides)
        run_cmd._validate_merged_overrides(overrides)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(exit_codes.USER_ERROR) from exc

    # Ensure max_actions is present unless user already set it via --set.
    agents = dict((overrides or {}).get("agents") or {})
    actor = dict(agents.get("actor") or {})
    if "max_actions_per_step" not in actor and "max_actions_per_step" not in agents:
        actor["max_actions_per_step"] = max_actions_per_step
        agents["actor"] = actor
        overrides = dict(overrides or {})
        overrides["agents"] = agents

    try:
        resolved_loop_id, loop_id_source = _resolve_loop_id(loop_id, set_loop_id)
    except ValueError as exc:
        print_error(
            str(exc),
            hint=(
                "Example:\n"
                "  python3 -m tools.cli loop ssos_eclss_loop \\\n"
                "    --backend plant_sim \\\n"
                "    --actor-mode labeled_rule_base \\\n"
                "    --design-mode labeled_rule_base \\\n"
                "    --inject-failures \\\n"
                "    --steps 50 \\\n"
                "    --loop-id e003loop"
            ),
        )
        raise typer.Exit(exit_codes.USER_ERROR) from exc

    try:
        from scenario.jobs.resolve import sanitize_run_id

        resolved_loop_id = sanitize_run_id(resolved_loop_id)
    except ValueError as exc:
        print_error(str(exc), hint="Example: --loop-id e003loop")
        raise typer.Exit(exit_codes.USER_ERROR) from exc

    spec = LoopSpec(
        scenario=scenario_name,
        overrides=overrides,
        results_root=results_root,
        loop_id=resolved_loop_id,
        max_loops=max_loops,
        target_crew=target_crew,
        max_actions_per_step=max_actions_per_step,
        seed=seed,
    )

    if not quiet and not json_output:
        first_id = spec.run_id_for(1)
        last_id = spec.run_id_for(max_loops)
        # markup=False avoids Rich mis-parsing ids that contain brackets/digits.
        console.print(
            f"loop {scenario_name}\n"
            f"  loop_id={resolved_loop_id}  (from {loop_id_source})\n"
            f"  run_ids={first_id} .. {last_id}\n"
            f"  max_loops={max_loops}  target_crew={target_crew}  "
            f"max_actions_per_step={max_actions_per_step}",
            markup=False,
        )

    if dry_run:
        plan = {
            "scenario": scenario_name,
            "max_loops": max_loops,
            "target_crew": target_crew,
            "loop_id": resolved_loop_id,
            "loop_id_source": loop_id_source,
            "run_ids": [spec.run_id_for(i) for i in range(1, max_loops + 1)],
            "overrides": overrides,
        }
        if json_output:
            typer.echo(__import__("json").dumps(plan, ensure_ascii=False, indent=2, default=str))
        else:
            console.print(plan)
        raise typer.Exit(exit_codes.SUCCESS)

    if run_cmd._any_llm_mode(scenario_name, overrides):
        env_code = run_cmd._preflight_llm(scenario_name, overrides)
        if env_code != 0:
            raise typer.Exit(env_code)

    result = execute_loop(spec)
    if json_output:
        typer.echo(__import__("json").dumps(result.to_dict(), ensure_ascii=False, indent=2))
    elif quiet:
        console.print(str(result.manifest_path or ""), markup=False)
    else:
        console.print(
            f"loop done reason={result.stopped_reason}  "
            f"runs={len(result.runs)}  target_met={result.target_met}  "
            f"manifest={result.manifest_path}",
            markup=False,
        )
        for entry in result.history:
            summary = entry.get("summary") or {}
            console.print(
                f"  {entry.get('run_id')}: crew_remaining="
                f"{summary.get('crew_remaining')}  "
                f"proposals={summary.get('design_proposal_count')}",
                markup=False,
            )

    if any(r.exit_code != 0 for r in result.runs):
        raise typer.Exit(exit_codes.RUN_FAILURE)
    raise typer.Exit(exit_codes.SUCCESS)


def _extract_loop_id_from_sets(set_values: List[str]) -> Tuple[Optional[str], List[str]]:
    """Pull loop_id=... / loop.id=... out of --set so it does not enter scenario YAML."""
    found: Optional[str] = None
    kept: List[str] = []
    for item in set_values:
        if "=" not in item:
            kept.append(item)
            continue
        key, value = item.split("=", 1)
        key_n = key.strip().lower().replace("-", "_")
        if key_n in {"loop_id", "loop.id", "output.loop_id"}:
            found = value.strip()
            continue
        kept.append(item)
    return found, kept


def _resolve_loop_id(
    cli_value: Optional[str],
    set_value: Optional[str] = None,
) -> tuple[str, str]:
    """Return (loop_id, source_label). CLI > --set > EA_LOOP_ID. No silent default."""
    if cli_value is not None and str(cli_value).strip():
        return str(cli_value).strip(), "--loop-id/--run-id"
    if set_value is not None and str(set_value).strip():
        return str(set_value).strip(), "--set loop_id="
    env_value = os.environ.get(LOOP_ID_ENV_VAR)
    if env_value is not None and str(env_value).strip():
        return str(env_value).strip(), LOOP_ID_ENV_VAR
    raise ValueError(
        "loop_id is required. Pass --loop-id e003loop "
        "(or --run-id e003loop / EA_LOOP_ID / --set loop_id=e003loop). "
        "Without it, results would silently use e002loop."
    )
