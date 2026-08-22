"""Interactive plant_sim sensitivity — not the run dashboard.

Usage::

    python3 -m tools.plant_sim_sensitivity_app

or::

    python3 -m streamlit run src/tools/plant_sim_sensitivity_app.py --server.port 8502
"""

from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import matplotlib.pyplot as plt
import streamlit as st

from tools.plant_sim_sensitivity import (
    SLIDER_SPECS,
    SliderSpec,
    SweepRow,
    run_sensitivity,
    sensitivity_figure,
    yaml_defaults,
)

APP_PATH = Path(__file__).resolve()
DEFAULT_PORT = "8502"


def _in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def launch(argv: Iterable[str] | None = None) -> int:
    extra = list(argv) if argv is not None else sys.argv[1:]
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_PATH),
        "--server.headless",
        "true",
        "--server.port",
        DEFAULT_PORT,
        "--browser.gatherUsageStats",
        "false",
    ]
    cmd.extend(extra)
    return subprocess.call(cmd)


@st.cache_data(show_spinner="Running plant_sim sweep…")
def cached_sweep(items: Tuple[Tuple[str, float], ...], n_max: int, steps: int) -> List[SweepRow]:
    rows, _patched = run_sensitivity(dict(items), n_max=n_max, steps=steps)
    return rows


def _slider(spec: SliderSpec, default: float) -> float | int:
    label = f"{spec.label} [{spec.unit}]"
    if spec.kind == "int":
        return st.slider(
            label,
            min_value=int(spec.minimum),
            max_value=int(spec.maximum),
            value=int(default),
            step=max(1, int(spec.step)),
            key=spec.key,
        )
    return st.slider(
        label,
        min_value=float(spec.minimum),
        max_value=float(spec.maximum),
        value=float(default),
        step=float(spec.step),
        key=spec.key,
    )


def render() -> None:
    st.set_page_config(page_title="plant_sim sensitivity", layout="wide")
    st.title("plant_sim sensitivity")
    st.caption(
        "Not the Streamlit run dashboard. Sliders patch scenario.yaml in memory "
        "(initial storage + plant_sim). Survival stays off. Dashed lines are the YAML baseline. "
        "Crew water sinks are rescaled so urine + condensate + unrecoverable = potable."
    )

    defaults = yaml_defaults()
    grouped: Dict[str, List[SliderSpec]] = defaultdict(list)
    for spec in SLIDER_SPECS:
        grouped[spec.group].append(spec)

    with st.sidebar:
        st.header("scenario.yaml knobs")
        if st.button("Reset to YAML", use_container_width=True):
            for spec in SLIDER_SPECS:
                st.session_state[spec.key] = defaults[spec.key]
            st.rerun()
        n_max = st.slider("N max (x-axis)", min_value=2, max_value=64, value=8, step=1)
        steps = st.slider("Campaign steps", min_value=4, max_value=36, value=20, step=1)
        overlay = st.checkbox("Overlay YAML baseline", value=True)
        overrides: Dict[str, Any] = {}
        for group, specs in grouped.items():
            with st.expander(group, expanded=(group in {"Initial storage", "Crew"})):
                for spec in specs:
                    overrides[spec.key] = _slider(spec, defaults[spec.key])

    yaml_n = int(overrides["plant_sim.crew.size"])
    payload = tuple(sorted((k, float(v)) for k, v in overrides.items()))
    current = cached_sweep(payload, n_max, steps)
    baseline = None
    if overlay:
        baseline = cached_sweep(tuple(sorted((k, float(v)) for k, v in defaults.items())), n_max, steps)
    fig = sensitivity_figure(current, baseline_rows=baseline, yaml_n=yaml_n)
    st.pyplot(fig, clear_figure=True, use_container_width=True)
    plt.close(fig)
    st.markdown(
        "- **Crew metabolism**: unconstrained demand ∝ N × activity × rates × dt/86400.\n"
        "- **One subsystem action**: ARS/OGS/WRS nameplate, inventory ignored.\n"
        "- **Tank inventory**: simulated Δ tank / step from `simulation.initial_*`.\n"
        "- **Tank + initial**: ending tank = initial + campaign Δ (own y-scale; dotted = initial fill).\n"
        "- Dotted vertical line: `plant_sim.crew.size` (scenario operating point; x-axis still sweeps N)."
    )


if _in_streamlit():
    render()
elif __name__ == "__main__":
    raise SystemExit(launch())
