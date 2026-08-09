"""Tests for Step Replay navigation edge cases."""

from streamlit.testing.v1 import AppTest

from tools.dashboard.app import _should_show_step_slider


def test_should_show_step_slider_requires_strictly_increasing_bounds():
    assert _should_show_step_slider(1) is False
    assert _should_show_step_slider(0) is False
    assert _should_show_step_slider(2) is True


def test_step_nav_controls_single_step_run_does_not_raise():
    app = AppTest.from_string(
        """
from tools.dashboard.app import _step_nav_controls
import streamlit as st

step = _step_nav_controls(
    step_key="replay_step",
    max_step=1,
    slider_label="Replay step",
    key_prefix="replay",
)
st.write(step)
"""
    )
    app.run()
    assert not app.exception
    assert list(app.slider) == []
    captions = [c.value for c in app.caption]
    assert any("single-step run" in value for value in captions)
    assert app.button[0].disabled is True
    assert app.button[1].disabled is True
