"""Loop command — multi-run design→verification orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from scenario.jobs.loop import (
    DEFAULT_LOOP_ID,
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
    loop_id: str = typer.Option(
        DEFAULT_LOOP_ID,
        "--loop-id",
        "--run-id",
        help=(
            "Prefix for result directories and run ids "
            "(e.g. e003loop → e003loop-run01). Alias: --run-id."
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
            set_values=set_values,
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

    spec = LoopSpec(
        scenario=scenario_name,
        overrides=overrides,
        results_root=results_root,
        loop_id=loop_id,
        max_loops=max_loops,
        target_crew=target_crew,
        max_actions_per_step=max_actions_per_step,
        seed=seed,
    )

    if not quiet and not json_output:
        console.print(
            f"[cyan]loop[/cyan] {scenario_name}  "
            f"loop_id={loop_id}  "
            f"max_loops={max_loops}  target_crew={target_crew}  "
            f"run_ids={spec.run_id_for(1)}…{spec.run_id_for(max_loops)}  "
            f"max_actions_per_step={max_actions_per_step}"
        )

    if dry_run:
        plan = {
            "scenario": scenario_name,
            "max_loops": max_loops,
            "target_crew": target_crew,
            "loop_id": loop_id,
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
        console.print(str(result.manifest_path or ""))
    else:
        console.print(
            f"[green]loop done[/green] reason={result.stopped_reason}  "
            f"runs={len(result.runs)}  target_met={result.target_met}  "
            f"manifest={result.manifest_path}"
        )
        for entry in result.history:
            summary = entry.get("summary") or {}
            console.print(
                f"  {entry.get('run_id')}: crew_remaining="
                f"{summary.get('crew_remaining')}  "
                f"proposals={summary.get('design_proposal_count')}"
            )

    if any(r.exit_code != 0 for r in result.runs):
        raise typer.Exit(exit_codes.RUN_FAILURE)
    raise typer.Exit(exit_codes.SUCCESS)
