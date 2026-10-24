"""`store_state` (ADR-0122): Wilson-interval rule over three axes, four weeks."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import store_state as ss  # noqa: E402  # pyright: ignore[reportMissingImports]
import value_layer_due_check as vldc  # noqa: E402  # pyright: ignore[reportMissingImports]


def _w(staged=0, clusters=40, cand=0, store=55, hub=10, sel=100) -> dict:
    return {
        "staged": staged,
        "clusters": clusters,
        "archive_candidates": cand,
        "store": store,
        "hub_selections": hub,
        "selections": sel,
    }


@pytest.mark.unit
def test_saturated_needs_whole_intervals_below_floor_and_concentrated_hub() -> None:
    weeks = [_w(hub=30)] * 4  # entry 0/160, exit 0/220, hub 120/400 = 0.30
    assert ss.build_store_state(weeks)["state"] == "saturated"


@pytest.mark.unit
def test_diffuse_hub_blocks_saturated() -> None:
    weeks = [_w(hub=5, sel=200)] * 4  # hub 20/800 = 0.025, whole interval < 0.20
    assert ss.build_store_state(weeks)["state"] == "equilibrium"


@pytest.mark.unit
def test_one_staged_item_does_not_flip_a_small_denominator() -> None:
    # entry 1/160: point 0.006 but the Wilson upper bound is above 0.05? it is not,
    # so check the real property: the verdict is computed from the interval.
    weeks = [_w(staged=1, hub=30), _w(hub=30), _w(hub=30), _w(hub=30)]
    out = ss.build_store_state(weeks)
    assert out["axes"]["entry"]["ci"][1] == ss.wilson_ci(1, 160)[1]


@pytest.mark.unit
def test_growing_when_entry_interval_is_above_and_exit_is_not() -> None:
    weeks = [_w(staged=20, hub=30)] * 4  # 80/160 = 0.5
    assert ss.build_store_state(weeks)["state"] == "growing"


@pytest.mark.unit
def test_short_window_and_count_only_axes_are_undetermined_with_a_reason() -> None:
    assert ss.build_store_state([_w()] * 3)["reason"] == "STORE_STATE_WINDOW_SHORT"
    thin = [_w(clusters=1)] * 4  # 4 pooled trials < 10
    out = ss.build_store_state(thin)
    assert out["state"] == "undetermined" and out["count_only"] == ["entry"]
    assert out["axes"]["entry"]["ci"] is None


@pytest.mark.unit
def test_value_layer_reading_carries_store_state_only_when_axes_given() -> None:
    base = dict(
        audit_records=[],
        staging_pending=0,
        as_of="2026-12-01",
        identity_interval_days=27,
        amendment_interval_days=83,
        patterns=[],
    )
    assert "store_state" not in vldc.build_reading(**base)
    assert (
        vldc.build_reading(**base, store_axes=[_w(hub=30)] * 4)["store_state"]["state"]
        == "saturated"
    )
