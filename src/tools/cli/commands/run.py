"""Run command — execute a single simulation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import typer

from core.llm.factory import VALID_LLM_PROVIDERS, describe_llm_target
from scenario.jobs.executor import execute_run
from scenario.jobs.spec import RunSpec
from scenario.runner import load_agents_config, load_scenario_config, scenario_descriptions
from tools.cli import exit_codes
from tools.cli.output import print_error, print_run_plan, print_run_result
from tools.cli.overrides import load_override_file, merge_overrides, parse_set_values

DEFAULT_SCENARIO = "scrubber_degradation"
VALID_AGENTS_MODES = frozenset({"none", "labeled_rule_base", "llm"})
VALID_SSOS_BACKENDS = frozenset({"mock", "plant_sim", "ros2"})
BACKEND_ENV_VAR = "SSOS_ECLSS_BACKEND"


def register(app: typer.Typer) -> None:
    app.command("run")(run)


def run(
    scenario: Optional[str] = typer.Argument(
        None,
        help="Scenario name (default: scrubber_degradation).",
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
        help="Agent mode: none, labeled_rule_base, or llm. On ssos_eclss_loop, alias for --actor-mode.",
    ),
    steps: Optional[int] = typer.Option(None, "--steps", help="Override simulation.steps."),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Override output run id."),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Explicit output directory.",
    ),
    results_root: Optional[Path] = typer.Option(
        None,
        "--results-root",
        help="Override results base directory.",
    ),
    backend: Optional[str] = typer.Option(
        None,
        "--backend",
        help="ssos_eclss_loop backend kind: mock, plant_sim, or ros2.",
    ),
    apply_proposals: Optional[Path] = typer.Option(
        None,
        "--apply-proposals",
        help="Apply design_proposals.json before running (ssos_eclss_loop).",
    ),
    llm_provider: Optional[str] = typer.Option(
        None,
        "--llm-provider",
        help=(
            "LLM backend for sides whose mode is llm: ollama (local) or vllm "
            "(lab GPU server). On ssos_eclss_loop, non-llm sides are left unchanged."
        ),
    ),
    llm_model: Optional[str] = typer.Option(
        None,
        "--llm-model",
        help=(
            "Override llm.model on sides whose mode is llm "
            "(Ollama tag or vLLM served-model id)."
        ),
    ),
    inject_failures: Optional[bool] = typer.Option(
        None,
        "--inject-failures/--no-inject-failures",
        help=(
            "Apply the ssos_eclss_loop subsystem_failures schedule. "
            "Default: off (scenario.yaml inject_failures)."
        ),
    ),
    seed: Optional[int] = typer.Option(None, "--seed", help="Record a reproducibility seed."),
    set_values: List[str] = typer.Option(
        [],
        "--set",
        help="Deep override using dot notation (example: simulation.steps=30).",
    ),
    override_file: Optional[Path] = typer.Option(
        None,
        "--override-file",
        help="YAML or JSON patch merged into scenario config.",
    ),
    no_recreate: bool = typer.Option(
        False,
        "--no-recreate",
        help="Do not delete an existing output directory before running.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build the run plan without executing."),
    write_spec: Optional[Path] = typer.Option(
        None,
        "--write-spec",
        help="Write the resolved RunSpec JSON to PATH.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    quiet: bool = typer.Option(False, "--quiet", help="Print only the output path."),
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

    try:
        overrides = _build_overrides(
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
        overrides = _apply_cli_defaults(scenario_name, overrides)
        overrides = _apply_llm_cli_to_llm_sides(
            scenario_name, overrides, llm_provider=llm_provider, llm_model=llm_model
        )
        overrides = _materialize_resolved_llm(scenario_name, overrides)
        _validate_merged_overrides(overrides)
    except ValueError as exc:
        print_error(str(exc), hint="Example: --set simulation.steps=30")
        raise typer.Exit(exit_codes.USER_ERROR) from exc

    spec = RunSpec(
        scenario=scenario_name,
        overrides=overrides,
        output_dir=output_dir,
        run_id=run_id,
        results_root=results_root,
        recreate_output=not no_recreate,
        seed=seed,
        apply_proposals_path=apply_proposals,
    )

    if write_spec is not None:
        spec.write_json(write_spec)

    resolved_mode = _resolved_display_mode(scenario_name, overrides)
    resolved_steps = (overrides or {}).get("simulation", {}).get("steps")
    if resolved_steps is None:
        config = load_scenario_config(scenario_name, overrides)
        resolved_steps = (config.get("simulation") or {}).get("steps")

    extra_lines = {}
    if backend:
        extra_lines["backend"] = backend
    if apply_proposals:
        extra_lines["apply_proposals"] = str(apply_proposals)
    if inject_failures is not None:
        extra_lines["inject_failures"] = str(inject_failures).lower()
    if llm_provider:
        extra_lines["llm_provider"] = llm_provider
    if llm_model:
        extra_lines["llm_model"] = llm_model

    if not quiet and not json_output:
        print_run_plan(
            scenario_name,
            str(resolved_mode),
            int(resolved_steps) if resolved_steps is not None else None,
            extra_lines=extra_lines or None,
        )

    if dry_run:
        if json_output:
            typer.echo(spec.to_json())
        raise typer.Exit(exit_codes.SUCCESS)

    if _any_llm_mode(scenario_name, overrides):
        env_code = _preflight_llm(scenario_name, overrides)
        if env_code != exit_codes.SUCCESS:
            raise typer.Exit(env_code)

    if not quiet and not json_output:
        typer.echo("Running simulation...")

    from tools.cli.ssos_host import (
        check_ssos_ros2_host_environment,
        run_ssos_in_container,
        should_run_ssos_in_container,
    )

    env_block = check_ssos_ros2_host_environment(spec)
    if env_block is not None:
        result = env_block
    elif should_run_ssos_in_container(spec):
        result = run_ssos_in_container(spec)
    else:
        result = execute_run(spec)
    print_run_result(result, quiet=quiet, as_json=json_output)
    if result.exit_code != 0:
        print_error(result.error or "Simulation failed.")
        raise typer.Exit(result.exit_code)
    raise typer.Exit(exit_codes.SUCCESS)


def _resolved_display_mode(scenario_name: str, overrides: dict | None) -> str:
    config = load_scenario_config(scenario_name, overrides)
    if scenario_name == "ssos_eclss_loop":
        from scenario.ssos_eclss_loop.agent_config import resolve_ssos_modes

        agents_config = load_agents_config(scenario_name, config) or {}
        actor_mode, design_mode = resolve_ssos_modes(agents_config)
        if actor_mode == design_mode:
            return actor_mode
        return f"actor={actor_mode} design={design_mode}"
    return str((config.get("agents") or {}).get("mode", "none"))


def _any_llm_mode(scenario_name: str, overrides: dict | None) -> bool:
    config = load_scenario_config(scenario_name, overrides)
    if scenario_name != "ssos_eclss_loop":
        return (config.get("agents") or {}).get("mode") == "llm"
    agents_config = load_agents_config(scenario_name, config) or {}
    from scenario.ssos_eclss_loop.agent_config import resolve_ssos_modes

    actor_mode, design_mode = resolve_ssos_modes(agents_config)
    return actor_mode == "llm" or design_mode == "llm"


def _require_mode(value: str, label: str) -> str:
    if value not in VALID_AGENTS_MODES:
        allowed = ", ".join(sorted(VALID_AGENTS_MODES))
        raise ValueError(f"Unsupported {label}: {value!r}. Choose one of: {allowed}")
    return value


def _build_overrides(
    *,
    scenario_name: str,
    agents_mode: Optional[str],
    actor_mode: Optional[str] = None,
    design_mode: Optional[str] = None,
    steps: Optional[int],
    backend: Optional[str],
    inject_failures: Optional[bool],
    set_values: List[str],
    override_file: Optional[Path],
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
) -> dict | None:
    parts = []
    ssos = scenario_name == "ssos_eclss_loop"
    if ssos and agents_mode is not None and actor_mode is not None:
        raise ValueError("Specify only one of --actor-mode and --agents-mode")
    if ssos:
        resolved_actor = actor_mode or agents_mode
        if resolved_actor is not None:
            parts.append({"agents": {"actor": {"mode": _require_mode(resolved_actor, "actor mode")}}})
        if design_mode is not None:
            parts.append({"agents": {"design": {"mode": _require_mode(design_mode, "design mode")}}})
    elif agents_mode is not None:
        parts.append({"agents": {"mode": _require_mode(agents_mode, "agents mode")}})
    elif actor_mode is not None or design_mode is not None:
        raise ValueError("--actor-mode and --design-mode apply only to ssos_eclss_loop")
    if steps is not None:
        parts.append({"simulation": {"steps": steps}})
    if backend is not None:
        if backend not in VALID_SSOS_BACKENDS:
            allowed = ", ".join(sorted(VALID_SSOS_BACKENDS))
            raise ValueError(
                f"Unsupported backend kind: {backend!r}. Choose one of: {allowed}"
            )
        parts.append({"backend": {"kind": backend}})
    if inject_failures is not None:
        parts.append({"inject_failures": inject_failures})
    if llm_provider is not None:
        provider = llm_provider.strip().lower()
        if provider not in VALID_LLM_PROVIDERS:
            allowed = ", ".join(sorted(VALID_LLM_PROVIDERS))
            raise ValueError(
                f"Unsupported LLM provider: {llm_provider!r}. Choose one of: {allowed}"
            )
        llm_patch = {"provider": provider}
        if not ssos:
            parts.append({"agents": {"llm": llm_patch}})
    if llm_model is not None and not ssos:
        parts.append({"agents": {"llm": {"model": llm_model}}})
    if set_values:
        parts.append(parse_set_values(set_values))
    if override_file is not None:
        parts.append(load_override_file(override_file))
    return merge_overrides(*parts)


def _apply_cli_defaults(scenario_name: str, overrides: dict | None) -> dict | None:
    """Inject CLI-only defaults that differ from scenario.yaml (not for --set/--override-file)."""
    if scenario_name != "ssos_eclss_loop":
        return overrides
    merged = dict(overrides or {})
    backend_kind = (merged.get("backend") or {}).get("kind")
    if backend_kind or os.environ.get(BACKEND_ENV_VAR):
        return merged
    return merge_overrides(merged, {"backend": {"kind": "ros2"}})


def _apply_llm_cli_to_llm_sides(
    scenario_name: str,
    overrides: dict | None,
    *,
    llm_provider: Optional[str],
    llm_model: Optional[str],
) -> dict | None:
    """Stamp ``--llm-provider`` / ``--llm-model`` only onto sides whose mode is llm."""
    if scenario_name != "ssos_eclss_loop" or (llm_provider is None and llm_model is None):
        return overrides
    scenario_config = load_scenario_config(scenario_name, overrides)
    agents_config = load_agents_config(scenario_name, scenario_config) or {}
    from scenario.ssos_eclss_loop.agent_config import iter_ssos_llm_targets

    llm_patch: dict = {}
    if llm_provider is not None:
        llm_patch["provider"] = llm_provider.strip().lower()
    if llm_model is not None:
        llm_patch["model"] = llm_model
    if not llm_patch:
        return overrides
    patch: dict = {"agents": {}}
    for side, _cfg in iter_ssos_llm_targets(agents_config):
        patch["agents"][side] = {"llm": dict(llm_patch)}
    if not patch["agents"]:
        return overrides
    return merge_overrides(overrides or {}, patch)


def _materialize_resolved_llm(scenario_name: str, overrides: dict | None) -> dict | None:
    """Bake env/CLI-resolved provider, URL, and model into the RunSpec.

    Host preflight honors ``LLM_PROVIDER`` / ``VLLM_*``, but the SSOS container
    job only sees ``overrides``. Without this, yaml ``provider: ollama`` wins
    inside the container after vLLM already passed on the host.
    """
    scenario_config = load_scenario_config(scenario_name, overrides)
    if scenario_name == "ssos_eclss_loop":
        from scenario.ssos_eclss_loop.agent_config import resolve_ssos_modes

        agents_config = load_agents_config(scenario_name, scenario_config) or {}
        actor_mode, design_mode = resolve_ssos_modes(agents_config)
        patch: dict = {"agents": {}}
        if actor_mode == "llm":
            actor_llm = (agents_config.get("actor") or {}).get("llm") or {}
            provider, base_url, model = describe_llm_target(actor_llm)
            patch["agents"]["actor"] = {
                "llm": {"provider": provider, "base_url": base_url, "model": model}
            }
        if design_mode == "llm":
            design_llm = (agents_config.get("design") or {}).get("llm") or {}
            provider, base_url, model = describe_llm_target(design_llm)
            patch["agents"]["design"] = {
                "llm": {"provider": provider, "base_url": base_url, "model": model}
            }
        if not patch["agents"]:
            return overrides
        return merge_overrides(overrides or {}, patch)

    mode = (scenario_config.get("agents") or {}).get("mode", "none")
    if mode != "llm":
        return overrides
    agents_config = load_agents_config(scenario_name, scenario_config) or {}
    llm_cfg = agents_config.get("llm") or {}
    provider, base_url, model = describe_llm_target(llm_cfg)
    return merge_overrides(
        overrides or {},
        {"agents": {"llm": {"provider": provider, "base_url": base_url, "model": model}}},
    )


def _validate_merged_overrides(overrides: dict | None) -> None:
    if not overrides:
        return
    agents = overrides.get("agents") or {}
    for key, label in (
        ("mode", "agents mode"),
        ("actor", "actor mode"),
        ("design", "design mode"),
    ):
        if key == "mode":
            value = agents.get("mode")
        else:
            value = (agents.get(key) or {}).get("mode") if isinstance(agents.get(key), dict) else None
        if value is not None and value not in VALID_AGENTS_MODES:
            allowed = ", ".join(sorted(VALID_AGENTS_MODES))
            raise ValueError(f"Unsupported {label}: {value!r}. Choose one of: {allowed}")
    backend_kind = (overrides.get("backend") or {}).get("kind")
    if backend_kind is not None and backend_kind not in VALID_SSOS_BACKENDS:
        allowed = ", ".join(sorted(VALID_SSOS_BACKENDS))
        raise ValueError(
            f"Unsupported backend kind: {backend_kind!r}. Choose one of: {allowed}"
        )
    llm_provider = ((overrides.get("agents") or {}).get("llm") or {}).get("provider")
    if llm_provider is not None:
        provider = str(llm_provider).strip().lower()
        if provider not in VALID_LLM_PROVIDERS:
            allowed = ", ".join(sorted(VALID_LLM_PROVIDERS))
            raise ValueError(
                f"Unsupported LLM provider: {llm_provider!r}. Choose one of: {allowed}"
            )


def _preflight_llm_targets(scenario_name: str, overrides: dict | None) -> list[tuple[str, dict]]:
    """Return (label, llm_cfg) pairs for every enabled LLM endpoint."""
    scenario_config = load_scenario_config(scenario_name, overrides)
    agents_config = load_agents_config(scenario_name, scenario_config) or {}
    if scenario_name != "ssos_eclss_loop":
        return [("agents", agents_config.get("llm", {}) or {})]
    from scenario.ssos_eclss_loop.agent_config import iter_ssos_llm_targets

    return iter_ssos_llm_targets(agents_config)


def _preflight_llm(scenario_name: str, overrides: dict | None) -> int:
    from core.llm.factory import build_llm_client, describe_llm_target

    seen: set[tuple[str, str, str]] = set()
    for side, llm_cfg in _preflight_llm_targets(scenario_name, overrides):
        try:
            provider, base_url, model = describe_llm_target(llm_cfg)
            client = build_llm_client(llm_cfg)
        except ValueError as exc:
            print_error(str(exc), hint="Use --llm-provider ollama or vllm")
            return exit_codes.USER_ERROR
        key = (provider, base_url, model)
        if key in seen:
            continue
        seen.add(key)
        if client.check_connection():
            continue
        side_label = f"{side} " if side != "agents" else ""
        if provider == "vllm":
            print_error(
                f"vLLM is not reachable for {side_label}llm mode.",
                hint=(
                    "Connect to the lab LAN or VPN and retry, or run: ea doctor\n"
                    f"Expected: {base_url}  model: {model}\n"
                    "Override with VLLM_BASE_URL or --set agents.actor.llm.base_url= / "
                    "agents.design.llm.base_url= (ssos) or agents.llm.base_url= (scrubber)"
                ),
            )
        else:
            print_error(
                f"Ollama is not reachable for {side_label}llm mode.",
                hint=f"Start Ollama and retry, or run: ea doctor\nExpected: {base_url}",
            )
        return exit_codes.ENVIRONMENT_ERROR
    return exit_codes.SUCCESS
