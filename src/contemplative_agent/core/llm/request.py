"""The parameters of one generation call, as values instead of a column of args.

The generation path threads nine concerns through five stacked frames
(``generate`` -> ``_generate_full`` -> ``_generate_impl`` -> ``_generate_via_backend``
/ ``_post_ollama``), all positionally. Two of them changed identity on the way
down — ``num_predict`` became ``effective_num_predict`` once the context-budget
clamp had run, and ``caller`` disappeared entirely because only telemetry still
needed it — so reading any one frame did not tell you what the frame above had
already decided.

Two types make that boundary explicit:

* :class:`GenerationRequest` is what the caller asked for.
* :class:`ResolvedRequest` is what will actually be sent, after the system
  prompt has been built and the output budget clamped to the context window.

Everything below the resolution step takes a ``ResolvedRequest``, so ``system``
is a ``str`` rather than ``str | None`` and ``num_predict`` is the final value —
the types say which stage you are in.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

DEFAULT_NUM_PREDICT = 8192
"""Output-token ceiling when a caller does not set one."""


@dataclass(frozen=True)
class GenerationRequest:
    """What the caller asked for, before the system prompt or budget is known.

    Field semantics are documented on :func:`contemplative_agent.core.llm.generate`,
    the public entry point whose signature this mirrors.
    """

    prompt: str
    system: str | None = None
    max_length: int | None = None
    num_predict: int | None = None
    format: dict | None = None
    temperature: float = 1.0
    drop_truncated: bool = False
    caller: str = "unknown"
    think: bool = False

    def resolve(self, system: str) -> ResolvedRequest:
        """Bind the built system prompt and the default output budget."""
        return ResolvedRequest(
            prompt=self.prompt,
            system=system,
            max_length=self.max_length,
            num_predict=(self.num_predict if self.num_predict is not None else DEFAULT_NUM_PREDICT),
            format=self.format,
            temperature=self.temperature,
            drop_truncated=self.drop_truncated,
            caller=self.caller,
            think=self.think,
        )

    @property
    def effective_num_predict(self) -> int:
        """The budget telemetry records before the context clamp can run."""
        return self.num_predict if self.num_predict is not None else DEFAULT_NUM_PREDICT


@dataclass(frozen=True)
class ResolvedRequest:
    """What will actually be sent: system prompt built, output budget final."""

    prompt: str
    system: str
    max_length: int | None
    num_predict: int
    format: dict | None
    temperature: float
    drop_truncated: bool
    caller: str
    think: bool

    def clamped_to(self, num_predict: int) -> ResolvedRequest:
        """Copy with a smaller output budget (context-window clamp, audit C2).

        Returns a new request rather than rebinding, so a frame that received
        this object cannot have its budget changed underneath it.
        """
        return replace(self, num_predict=num_predict)
