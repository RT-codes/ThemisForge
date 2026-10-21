from app.execution.harnesses.types import HarnessInfo, ModelInfo
from app.features.system.settings import AppSettings

HARNESSES = ("", "codex", "claude")  # "" = the placeholder program


AGENT_HARNESSES = ("codex", "claude")


_BASE = ("low", "medium", "high", "xhigh", "max")


CODEX_MODELS = (
    ModelInfo("gpt-6.1-sol", "GPT-6.1 Sol", (*_BASE, "ultra"), "low"),
    ModelInfo("gpt-6-astra", "GPT-6 Astra", (*_BASE, "ultra"), "low"),
    ModelInfo("gpt-6-sol", "GPT-6 Sol", (*_BASE, "ultra"), "medium"),
    ModelInfo("gpt-6-luna", "GPT-6 Luna", _BASE, "medium"),
    ModelInfo("gpt-5.6-sol", "GPT-5.6 Sol", (*_BASE, "ultra"), "low"),
    ModelInfo("gpt-5.6-terra", "GPT-5.6 Terra", (*_BASE, "ultra"), "medium"),
    ModelInfo("gpt-5.6-luna", "GPT-5.6 Luna", _BASE, "medium"),
)


CLAUDE_MODELS = (
    ModelInfo("claude-fable-5-1", "Fable 5.1", _BASE, "high"),
    ModelInfo("claude-opus-5-5", "Opus 5.5", _BASE, "high"),
    ModelInfo("claude-sonnet-5-5", "Sonnet 5.5", _BASE, "medium"),
    ModelInfo("claude-haiku-5-5", "Haiku 5.5", ("low", "medium", "high"), "medium"),
)


def effort_for(model: str, effort: str) -> str:
    """The effort a run really gets. The model, the effort or both can come from different layers (a workflow step
    overriding the model of an agent that asks for `ultra`), so an effort the model does not accept falls back to the
    model's own default instead of failing the run. A model that is not in the list is trusted as it is."""
    known = next((m for m in (*CODEX_MODELS, *CLAUDE_MODELS) if m.id == model), None)
    return known.default_effort if known and effort not in known.efforts else effort


CATALOG = (
    HarnessInfo(
        "codex",
        "Codex",
        "OpenAI's Codex CLI, signed in with your ChatGPT account (Settings, Codex).",
        supports_skills=True,
        supports_mcp=True,
        supports_keys=True,
        models=CODEX_MODELS,
    ),
    HarnessInfo(
        "claude",
        "Claude Code",
        "Anthropic's Claude Code CLI, signed in with your Claude subscription (Settings, Claude).",
        supports_skills=True,
        supports_mcp=True,
        supports_keys=True,
        models=CLAUDE_MODELS,
    ),
)


def defaults_for(harness: str, cfg: AppSettings) -> tuple[str, str, str]:
    """The (image, model, effort) Settings give a harness when an agent does not choose its own."""
    if harness == "claude":
        return cfg.claude_image, cfg.claude_model, cfg.claude_reasoning_effort
    return cfg.codex_image, cfg.codex_model, cfg.codex_reasoning_effort


def clean_model_name(v: str) -> str:
    """A model name ends up on a command line, so nothing a shell would treat specially gets through."""
    v = v.strip()
    if v and (v.startswith("-") or any(c.isspace() or c in "'\"$`\\;&|<>" for c in v)):
        raise ValueError("Invalid model name")
    return v
