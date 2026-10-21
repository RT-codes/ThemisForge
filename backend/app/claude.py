"""Claude Code as a connection: the account its runs are billed to.

Unlike GitHub, this is the login of a harness (see Provider.harness): every run of a Claude Code agent uses its
owner's connection, so nothing is chosen per project or agent. The secret is a Claude subscription token made with
`claude setup-token` (lasts a year, needs no refresh, so runs never have to take turns on it the way Codex's rotating
login does), or an Anthropic API key. A cell gets it as the variable Claude Code reads for that kind.
"""

from typing import Any

import httpx

from . import connections as base

API = "https://api.anthropic.com"
SUBSCRIPTION_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
API_KEY_ENV = "ANTHROPIC_API_KEY"
# `claude setup-token` prints sk-ant-oat01-..., an API key is sk-ant-api03-...
SUBSCRIPTION_PREFIX = "sk-ant-oat"
API_KEY_PREFIX = "sk-ant-api"


def kind_of(token: str) -> str:
    """Which sort of credential a token is, from how it starts: 'subscription', 'api' or '' for neither."""
    token = token.strip()
    if token.startswith(SUBSCRIPTION_PREFIX):
        return "subscription"
    return "api" if token.startswith(API_KEY_PREFIX) else ""


class ClaudeCode(base.Provider):
    id = "claude"
    name = "Claude Code"
    category = "ai"
    harness = "claude"
    description = "Runs Claude Code agents on your Claude subscription, or on an Anthropic API key."
    icon = "sparkles"
    token_help = (
        "Run `claude setup-token` in a terminal where Claude Code is installed, sign in, and paste the token it "
        "prints (it starts with sk-ant-oat). It uses your Claude plan and lasts a year. An Anthropic API key "
        "(sk-ant-api) works too and is billed per token."
    )
    env_names = (SUBSCRIPTION_ENV, API_KEY_ENV)

    def env_names_for(self, settings: dict[str, Any]) -> tuple[str, ...]:
        # exactly one: an empty ANTHROPIC_API_KEY next to a subscription token would make Claude Code prefer the key
        return (API_KEY_ENV,) if settings.get("kind") == "api" else (SUBSCRIPTION_ENV,)

    def secret_env(self, token: str) -> dict[str, str]:
        return {self.env_names_for({"kind": kind_of(token)})[0]: token}

    async def identify(self, token: str) -> base.Identity:
        token = token.strip()
        if any(c.isspace() for c in token) or not (kind := kind_of(token)):
            raise base.ConnectionProblem(
                "That does not look like a Claude token. Make one with `claude setup-token` "
                "(starts with sk-ant-oat) or use an Anthropic API key (starts with sk-ant-api)."
            )
        if kind == "api":
            await self._check_api_key(token)
        # A subscription token is limited to running Claude Code, so there is no API call that can vouch for it
        # here: a wrong one shows up as a login error in the first run instead.
        return base.Identity(
            account="Claude subscription" if kind == "subscription" else "Anthropic API key",
            settings={"kind": kind},
        )

    @staticmethod
    async def _check_api_key(token: str) -> None:
        try:
            async with base.http_client() as client:
                reply = await client.get(
                    f"{API}/v1/models", headers={"x-api-key": token, "anthropic-version": "2023-06-01"}
                )
        except httpx.HTTPError:
            raise base.ConnectionProblem(
                "Could not reach Anthropic. Check this server's internet connection."
            ) from None
        if reply.status_code in (401, 403):
            raise base.ConnectionProblem("Anthropic rejected that API key. Check that it is complete.")
        if reply.status_code != 200:
            raise base.ConnectionProblem(f"Anthropic answered with HTTP {reply.status_code}.")
