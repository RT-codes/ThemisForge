from dataclasses import astuple, dataclass, fields
from typing import Literal

AgentHarness = Literal[
    "codex", "claude"
]  # the same list, for schemas  # the ones that run an AI agent (so get keys, tools and a login)


Effort = Literal["low", "medium", "high", "xhigh", "max", "ultra"]


@dataclass(frozen=True)
class ModelInfo:
    """A model the editors offer in a dropdown, with the reasoning efforts it accepts."""

    id: str
    label: str
    efforts: tuple[str, ...]
    default_effort: str  # what Codex itself uses when no effort is asked for


@dataclass(frozen=True)
class HarnessInfo:
    """What the agent editor needs to know about a harness, so it only offers what the harness can do."""

    id: str
    label: str
    description: str
    supports_skills: bool = False
    supports_mcp: bool = False
    supports_keys: bool = False
    models: tuple[ModelInfo, ...] = ()  # empty: the harness has no model to choose


@dataclass(frozen=True)
class TokenUsage:
    """The tokens a run spent, as the harness reports them. Cached input is part of the input and reasoning part of
    the output, so the four numbers are not meant to be added up. Prices are worked out from these later, which is
    why they are kept as reported and not as money."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0

    @classmethod
    def from_event(cls, usage: dict) -> "TokenUsage":
        return cls(**{f.name: v for f in fields(cls) if isinstance(v := usage.get(f.name), int)})

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(*(a + b for a, b in zip(astuple(self), astuple(other), strict=True)))


@dataclass(frozen=True)
class HarnessPlan:
    image: str
    script: str
    writeback: tuple[str, ...] = ()
    # what the run is recorded under (see Attempt.model and Attempt.billing): the model after the defaults were filled
    # in, and how the harness is paid for
    model: str = ""
    billing: Literal["subscription", "api"] = "subscription"
