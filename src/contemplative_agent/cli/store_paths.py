"""Path predicates for the value-layer store, shared by every writer into it.

Six small functions, in one place because the containment argument only
holds if there is **one** implementation of each. ``adopt`` (the staged
write), ``skill_archive`` (the store's exit) and ``remove_skill`` all reach
the same store, and a second reader of "is this path inside" is how a
containment argument stops being one.

:func:`_target_inside_data_root` in particular tests the path on **both**
readings — the resolved referent and the literal path with a resolved parent
— because a read follows links and a rename does not. Either check alone
leaks in one direction; the docstring records which review found which
direction.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..adapters.moltbook import config

logger = logging.getLogger(__name__)


def _target_inside_data_root(target: Path, data_root: Path) -> bool:
    """Containment for a staged target, on BOTH readings of the path.

    The operations disagree about which reading they mean, so the check has
    to satisfy each. ``_print_system_budget_for_staged`` READS the target and
    a read follows every link, so the referent must be inside. The write
    (``write_restricted`` -> ``os.replace``) and the drop (``unlink``) act on
    the LITERAL path — they swap or remove the link itself, never its
    referent — so the literal location must be inside too. The parent IS
    resolved on the literal side, because ``os.replace`` follows parent
    symlinks; the same idiom ``_replaces_canonical_target`` settled on for
    the mirror-image bug found the same day.

    Checking only the referent let a symlink sitting OUTSIDE the store and
    pointing back in pass as "inside", after which the adoption landed
    outside (security review 2026-08-15, reproduced). Checking only the
    literal path would let a link inside the store expose an outside file to
    the reader.

    One predicate shared by the loader and the budget instrument, because
    the instrument's whole job is to project what the loop will do: an item
    the loop refuses must not appear in the reading the operator approves
    against (codex review 2026-08-15).
    """
    try:
        return target.resolve().is_relative_to(data_root) and (
            target.parent.resolve() / target.name
        ).is_relative_to(data_root)
    except OSError:
        return False


# Both halves of an ADR-0097 supersede pair go through
# ``core.text_utils.set_frontmatter_field`` with ``synthesize=True``: legacy
# skills predate the emitted block, and a lineage pointer stapled above a bare
# ``# Title`` would not be found by any frontmatter reader. The value is a
# *filename*, not the frontmatter ``name:`` slug — a slug is only unique per
# date (``slug_from_stem`` exists precisely because two files can share one),
# whereas restoring an archived skill is a plain ``mv`` and a ``mv`` needs a
# filename. Both halves are validated against real files before they are
# stamped, so the scalar is never free text.


def _resolved_or_self(path: Path) -> Path:
    """``path.resolve()``, falling back to *path* when the filesystem says no.

    Used only to compare two spellings of the same file. A resolve that
    raises must not take the comparison down with it; an unresolvable path
    simply compares as itself, which is the pre-existing behaviour.
    """
    try:
        return path.resolve()
    except OSError:
        return path


def _skills_dir(data_root: Path) -> Path:
    """The skill store, derived at call time.

    Not ``config.SKILLS_DIR``: that constant is frozen at import and every
    handler here honors a per-call / test-patched ``MOLTBOOK_HOME``. One
    function rather than five inline ``… / "skills"`` spellings, so a reader
    checking the containment argument does not first have to prove that the
    resolved and unresolved forms denote the same directory (code review
    2026-08-22). Callers pass an already-resolved *data_root*.
    """
    return data_root / config.SKILLS_DIRNAME


def _archive_dir(data_root: Path) -> Path:
    """The store's exit, one level inside the store."""
    return _skills_dir(data_root) / config.SKILLS_ARCHIVE_DIRNAME


def _inside_archive(path: Path, data_root: Path) -> bool:
    """Is *path* already inside the store's exit? Resolved on both sides.

    Two questions in ``remove-skill`` are this same predicate, and both were
    written out inline: the archive arm's "a file that already left has no
    second exit" refusal, and the audit row's purge-vs-remove discriminator.
    One function, so the two cannot answer differently — and so a reader
    checking either argument reads one implementation.

    Resolved on both sides because the interesting inputs are spellings, not
    files: ``remove-skill .archive/old`` names a nested path that the store
    containment check admits, and an ``.archive`` symlinked back into the
    store makes every live skill resolve inside it.
    """
    return _resolved_or_self(path).is_relative_to(_resolved_or_self(_archive_dir(data_root)))


def _writes_into_the_store(target: Path, data_root: Path) -> bool:
    """True when a staged item's target is a file directly in ``skills/``.

    The gate on a supersede successor: ADR-0097 D5 scopes both frontmatter
    halves to skills, and ``superseded_by: <name>`` only means anything if a
    ``mv`` back into ``skills/`` restores the pair. Applied twice on purpose —
    once in the plan for a fail-fast message with nothing touched, once at the
    write on the snapshot the write actually uses.

    The sidecar's ``target`` is attacker-chosen, so the loop's own containment
    test runs before the parent is compared; this is never a second, weaker
    reader of that field (module docstring).
    """
    return _target_inside_data_root(target, data_root) and _resolved_or_self(
        target.parent
    ) == _resolved_or_self(_skills_dir(data_root))
