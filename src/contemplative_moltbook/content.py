"""Content — backward-compatible re-export shim."""

from .adapters.moltbook.content import *  # noqa: F401,F403
from .adapters.moltbook.content import _content_hash  # noqa: F401
from .adapters.moltbook.content import __getattr__ as _adapter_getattr  # noqa: F401


def __getattr__(name: str) -> object:
    return _adapter_getattr(name)
