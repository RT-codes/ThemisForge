from collections.abc import Sequence

from app.execution.harnesses.catalog import defaults_for, effort_for
from app.execution.harnesses.claude import ClaudeRenderer, claude_script
from app.execution.harnesses.codex import CODEX_AUTH, CodexRenderer, codex_script
from app.execution.harnesses.rendering import HarnessRenderer
from app.execution.harnesses.types import HarnessPlan
from app.features.system.settings import AppSettings


def plan_for(
    harness: str, cfg: AppSettings, *, model: str = "", effort: str = "", key_envs: Sequence[str] = ()
) -> HarnessPlan | None:
    """None means the placeholder program, which needs nothing special. An agent may choose its own model and
    reasoning effort (empty means the ones in Settings) and be given keys, available as these variables."""
    if harness == "codex":
        image, default_model, default_effort = defaults_for(harness, cfg)
        model = model or default_model
        return HarnessPlan(
            image=image,
            script=codex_script(model, effort_for(model, effort or default_effort), key_envs),
            writeback=(CODEX_AUTH,),
            model=model,
            billing="subscription",  # Codex runs on the user's ChatGPT login, never on an API key
        )
    if harness == "claude":
        image, default_model, default_effort = defaults_for(harness, cfg)
        model = model or default_model
        return HarnessPlan(
            image=image,
            script=claude_script(model, effort_for(model, effort or default_effort), key_envs),
            model=model,
            # a subscription token bills the plan; an API key bills per token. The login says which (see the scheduler)
            billing="subscription",
        )
    return None


def renderer_for(harness: str) -> HarnessRenderer | None:
    return {"codex": CodexRenderer, "claude": ClaudeRenderer}.get(harness, lambda: None)()
