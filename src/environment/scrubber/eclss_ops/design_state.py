"""Mutable ECLSS topology and design parameters."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from environment.protocol import DesignState, TopologyEdge, TopologyGraph, TopologyNode


def default_topology() -> TopologyGraph:
    return TopologyGraph(
        nodes=[
            TopologyNode(id="cabin", name="Cabin", kind="volume"),
            TopologyNode(id="scrubber", name="CO2 Scrubber", kind="scrubber"),
            TopologyNode(id="manifold", name="Air Manifold", kind="manifold"),
            TopologyNode(id="power_bus", name="Power Bus", kind="electrical"),
        ],
        edges=[
            TopologyEdge(source="cabin", target="manifold", kind="flow"),
            TopologyEdge(source="manifold", target="scrubber", kind="flow"),
            TopologyEdge(source="scrubber", target="cabin", kind="flow"),
            TopologyEdge(source="power_bus", target="scrubber", kind="power"),
        ],
    )


def default_parameters() -> Dict[str, float]:
    return {
        "scrubber_base_efficiency": 0.95,
        "co2_production_ppm_per_step": 32.0,
        "scrub_rate_coefficient": 0.06,
        "fan_power_w": 80.0,
        "bypass_power_w": 40.0,
        "bypass_flow_bonus": 0.15,
        "permanent_bypass_power_w": 20.0,
        "load_reduction_factor": 0.6,
        "base_power_draw_w": 200.0,
        # Nameplate watts → power_margin_w units per step (single scale for all loads).
        # Default preserves prior equilibrium drain ≈4.8 at fan_speed=0.7:
        # (200 + 80*0.7) * 0.01875 = 4.8
        "power_draw_to_margin_factor": 0.01875,
        "eps_support_duration_steps": 5.0,
    }


class DesignStateManager:
    def __init__(
        self,
        topology: Optional[TopologyGraph] = None,
        parameters: Optional[Dict[str, float]] = None,
    ):
        self.topology = topology or default_topology()
        self.parameters = parameters or default_parameters()

    def snapshot(self) -> DesignState:
        return DesignState(
            topology=deepcopy(self.topology),
            parameters=dict(self.parameters),
        )

    def apply_dict_change(self, change_kind: str, payload: Dict[str, Any]) -> DesignState:
        """Apply a post-run proposal dict (scrubber dashboard preview / tests)."""
        if change_kind == "add_node":
            node = TopologyNode(
                id=payload["id"],
                name=payload.get("name", payload["id"]),
                kind=payload.get("kind", "volume"),
            )
            self.topology.nodes.append(node)
        elif change_kind == "add_edge":
            edge = TopologyEdge(
                source=payload["node_a"],
                target=payload["node_b"],
                kind=payload.get("kind", "bypass"),
            )
            self.topology.edges.append(edge)
        elif change_kind == "set_parameter":
            key = payload["key"]
            self.parameters[key] = float(payload["value"])
        else:
            raise ValueError(f"Unsupported design change kind: {change_kind}")
        return self.snapshot()

    def has_bypass_edge(self) -> bool:
        return any(e.kind == "bypass" for e in self.topology.edges)
