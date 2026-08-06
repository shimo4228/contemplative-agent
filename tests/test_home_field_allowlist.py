# pyright: reportAttributeAccessIssue=false
"""Allowlist gate for the /home dashboard consumption (T-HOME-STANDING-INSTRUCTIONS).

The platform's Labels system lets a submolt moderator attach a *role* to any
agent; roles carry a ``prompt`` delivered as a "standing instruction" briefing
inside the ``/home`` response (``check_in`` key, first observed 2026-08). That
is a third-party instruction-injection channel with no approval gate on our
side — it is safe only because the adapter drops it at the fetch boundary.

Two layers are pinned here:

1. **Projection** — ``_fetch_home_data`` stores only ``_HOME_ALLOWED_KEYS``,
   so briefing text never stays live in agent state. This is the load-bearing
   guard: any later code that serializes or iterates ``self._home_data``
   (``json.dumps``, ``{**home}``, a prompt f-string) physically cannot leak
   what was never stored.
2. **Access recording** — the direct consumers touch only allowlisted keys,
   so a change that starts reading ``check_in`` from the raw payload fails
   here and must argue its case against the injection boundary instead of
   landing silently.

Adopting briefings would also cut against observation-over-steering (no
external steering enters the loop unreviewed).
"""

import time
from unittest.mock import MagicMock

from contemplative_agent.adapters.moltbook.agent import (
    _HOME_ALLOWED_KEYS,
    Agent,
    AutonomyLevel,
)
from contemplative_agent.core.memory import MemoryStore

ALLOWED_HOME_KEYS = set(_HOME_ALLOWED_KEYS)

# The briefing payload a hostile (or merely enthusiastic) submolt could
# deliver. The sentinel makes any leak grep-able in assertion output.
SENTINEL = "INJECTED-STANDING-INSTRUCTION-7f3a"
UNCONSUMED_FIELDS = {
    "check_in": {"role": "battle-node", "prompt": SENTINEL},
    "what_to_do_next": [SENTINEL],
    "latest_moltbook_announcement": SENTINEL,
    "quick_links": [SENTINEL],
    "explore": [SENTINEL],
}


class KeyRecordingDict(dict):
    """A dict recording every top-level key access, including bulk shapes.

    ``items``/``keys``/``values``/``__iter__``/``copy`` record ALL keys: a
    consumer that serializes or iterates the payload (``json.dumps(dict(d))``,
    ``{**d}``, ``for k in d``) has observed every field, and the allowlist
    assertion must fail for it — those are exactly the leak shapes a
    ``.get``-only recorder waves through.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.accessed: set = set()

    def get(self, key, default=None):
        self.accessed.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.accessed.add(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self.accessed.add(key)
        return super().__contains__(key)

    def _touch_all(self):
        self.accessed.update(super().keys())

    def keys(self):
        self._touch_all()
        return super().keys()

    def values(self):
        self._touch_all()
        return super().values()

    def items(self):
        self._touch_all()
        return super().items()

    def __iter__(self):
        self._touch_all()
        return super().__iter__()

    def copy(self):
        self._touch_all()
        return super().copy()


def _make_agent(tmp_path) -> Agent:
    return Agent(
        autonomy=AutonomyLevel.AUTO,
        memory=MemoryStore(path=tmp_path / "memory.json"),
    )


def _home_payload() -> KeyRecordingDict:
    return KeyRecordingDict(
        {
            "your_account": {"id": "me-123", "name": "contemplative-agent"},
            "activity_on_your_posts": [
                {"post_id": "valid-post-1", "new_notification_count": 1},
            ],
            **UNCONSUMED_FIELDS,
        }
    )


class TestRecorderHasTeeth:
    """Self-test: the recorder must catch the bulk-access leak shapes."""

    def test_bulk_shapes_record_every_key(self):
        for shape in (dict, lambda d: {**d}, lambda d: list(d.items())):
            home = _home_payload()
            shape(home)
            assert "check_in" in home.accessed, f"leak shape not recorded: {shape}"


class TestHomeFieldAllowlist:
    def test_fetch_home_data_touches_only_allowed_keys(self, tmp_path):
        agent = _make_agent(tmp_path)
        home = _home_payload()
        client = MagicMock()
        client.get_home.return_value = home

        agent._fetch_home_data(client)

        assert home.accessed <= ALLOWED_HOME_KEYS, (
            f"/home keys outside the allowlist were consumed: "
            f"{home.accessed - ALLOWED_HOME_KEYS}. check_in carries "
            "third-party standing instructions — see module docstring."
        )

    def test_fetch_home_data_projects_before_storing(self, tmp_path):
        # The load-bearing guard: briefing fields must not survive into agent
        # state, so no later serialization/iteration of _home_data can leak
        # them into a prompt.
        agent = _make_agent(tmp_path)
        client = MagicMock()
        client.get_home.return_value = _home_payload()

        agent._fetch_home_data(client)

        assert set(agent._home_data) <= ALLOWED_HOME_KEYS
        assert SENTINEL not in repr(agent._home_data)

    def test_empty_projection_warns_instead_of_silently_degrading(self, tmp_path, caplog):
        # If the platform renames BOTH consumed fields — the exact event the
        # API drift scan exists to detect — the projection is empty and the
        # /home reply path degrades to the fallback cycle. That must be
        # visible (no silent fallback), but as a count only: the dropped key
        # names are platform text and *.log feeds LLM-facing reports.
        agent = _make_agent(tmp_path)
        client = MagicMock()
        client.get_home.return_value = dict(UNCONSUMED_FIELDS)

        with caplog.at_level("WARNING"):
            agent._fetch_home_data(client)

        warnings = [r for r in caplog.records if "no allowlisted keys" in r.getMessage()]
        assert warnings, "empty projection must warn"
        assert SENTINEL not in warnings[0].getMessage()

    def test_reply_cycle_touches_only_allowed_keys(self, tmp_path):
        agent = _make_agent(tmp_path)
        home = _home_payload()
        client = MagicMock()
        client.has_write_budget.return_value = True
        client.get_post_comments.return_value = []
        client.mark_notifications_read_by_post.return_value = True
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 60, home)

        assert home.accessed <= ALLOWED_HOME_KEYS, (
            f"/home keys outside the allowlist were consumed: {home.accessed - ALLOWED_HOME_KEYS}"
        )
