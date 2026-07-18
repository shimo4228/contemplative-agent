"""Allow ``python -m contemplative_agent.cli`` (parity with the former
single-file module's ``if __name__ == "__main__"`` block)."""

from . import main

if __name__ == "__main__":
    main()
