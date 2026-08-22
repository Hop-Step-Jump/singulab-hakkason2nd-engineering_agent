"""Resolve nested ssos_eclss_loop actor / design agent config."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

VALID_AGENT_MODES = frozenset({"none", "labeled_rule_base", "llm"})

_LEGACY_ACTOR_KEYS = (
    "mode",
    "team",
    "llm",
    "policy",
    "memory_limit",
    "discourse_window",
    "max_actions_per_step",
)


def _deep_merge_value(existing: Any, incoming: Any) -> Any:
    if isinstance(existing, dict) and isinstance(incoming, dict):
        out = dict(existing)
        for key, value in incoming.items():
            if key in out:
                out[key] = _deep_merge_value(out[key], value)
            else:
                out[key] = value
        return out
    return incoming


def _require_agent_mode(value: str, label: str) -> str:
    if value not in VALID_AGENT_MODES:
        allowed = ", ".join(sorted(VALID_AGENT_MODES))
        raise ValueError(f"Unsupported {label}: {value!r}. Choose one of: {allowed}")
    return value


def normalize_ssos_agents_section(section: Dict[str, Any]) -> Dict[str, Any]:
    """Lift legacy flat ``agents.mode`` / ``agents.team`` into ``actor`` / ``design``.

    Flat keys (including CLI ``--set agents.max_actions_per_step=8``) merge into
    the nested actor block and win over YAML defaults that already live there.
    """
    actor = dict(section.get("actor") or {})
    design = dict(section.get("design") or {})
    if "mode" in section:
        actor["mode"] = section["mode"]
    for key in _LEGACY_ACTOR_KEYS:
        if key == "mode":
            continue
        if key not in section:
            continue
        if key in actor:
            actor[key] = _deep_merge_value(actor[key], section[key])
        else:
            actor[key] = section[key]
    out = {
        k: v
        for k, v in section.items()
        if k not in _LEGACY_ACTOR_KEYS and k not in {"actor", "design", "config_file"}
    }
    out["actor"] = actor
    out["design"] = design
    return out


def resolve_ssos_modes(agents_config: Dict[str, Any]) -> Tuple[str, str]:
    """Return ``(actor_mode, design_mode)``.

    Omitted ``design.mode`` inherits ``actor.mode`` so a single ``--actor-mode``
    still runs post-run design. Independent endpoints stay allowed; CLI preflight
    must probe every enabled LLM side.
    """
    actor = agents_config.get("actor") or {}
    design = agents_config.get("design") or {}
    actor_mode = _require_agent_mode(str(actor.get("mode") or "none"), "actor mode")
    design_raw = design.get("mode")
    if design_raw is None:
        return actor_mode, actor_mode
    return actor_mode, _require_agent_mode(str(design_raw), "design mode")


def ssos_run_id_mode_key(agents_config: Dict[str, Any]) -> str:
    """Mode token used for default run ids.

    Matching actor/design modes keep the historical one-token ids. Mixed modes
    become ``{actor_mode}_{design_mode}`` so ``--design-mode llm`` cannot clobber
    a baseline or labeled results directory.
    """
    actor_mode, design_mode = resolve_ssos_modes(agents_config)
    if actor_mode == design_mode:
        return actor_mode
    return f"{actor_mode}_{design_mode}"


def iter_ssos_llm_targets(agents_config: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Enabled LLM sides and their ``llm`` blocks, in actor-then-design order."""
    actor_mode, design_mode = resolve_ssos_modes(agents_config)
    targets: List[Tuple[str, Dict[str, Any]]] = []
    if actor_mode == "llm":
        targets.append(("actor", dict((agents_config.get("actor") or {}).get("llm") or {})))
    if design_mode == "llm":
        targets.append(("design", dict((agents_config.get("design") or {}).get("llm") or {})))
    return targets


def flatten_actor_config(agents_config: Dict[str, Any]) -> Dict[str, Any]:
    actor = dict(agents_config.get("actor") or {})
    actor_mode, _ = resolve_ssos_modes(agents_config)
    actor["mode"] = actor_mode
    return actor


def flatten_design_config(agents_config: Dict[str, Any]) -> Dict[str, Any]:
    design = dict(agents_config.get("design") or {})
    _, design_mode = resolve_ssos_modes(agents_config)
    design["mode"] = design_mode
    return design


def ssos_agents_enabled(agents_config: Optional[Dict[str, Any]]) -> bool:
    if not agents_config:
        return False
    actor_mode, design_mode = resolve_ssos_modes(agents_config)
    return actor_mode != "none" or design_mode != "none"
