"""GitHub as a connection: the token's owner is who acts, so commits, issues and pull requests are theirs.

A cell gets the token as GH_TOKEN and GITHUB_TOKEN (secret, hidden from the log), and ordinary variables that make
`git` and `gh` work without any setup: a credential helper for github.com that answers with the token, the git author
of the token's owner, and the project's repository as gh's default.
"""

import re
from typing import Any

import httpx

from . import connections as base
from .app_settings import AppSettings

API = "https://api.github.com"
REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
# git runs a credential helper that starts with ! as a shell command; it answers only the "get" question
CREDENTIAL_HELPER = (
    '!f() { test "$1" = get && echo username=x-access-token && echo "password=$GH_TOKEN"; }; f'
)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _one_line(value: str, limit: int = 100) -> str:
    """A name from GitHub, made safe to put in an environment variable."""
    return " ".join(value.split())[:limit]


class GitHub(base.Provider):
    id = "github"
    name = "GitHub"
    category = "service"
    description = "Repositories, issues and pull requests. Agents use git and the gh command as the account that connects."
    icon = "git-branch"
    token_help = (
        "Create a fine-grained token at github.com/settings/personal-access-tokens. Pick the repositories agents "
        "should reach, and give it read and write on Contents, Issues and Pull requests."
    )
    device = base.DeviceFlow(
        code_url="https://github.com/login/device/code",
        token_url="https://github.com/login/oauth/access_token",
        scope="repo workflow read:org",
    )
    config_fields = (
        base.ConfigField(
            "repo",
            "Repository",
            "owner/name",
            "The repository this project works on. Agents are told about it. Leave empty for none.",
        ),
    )
    env_names = ("GH_TOKEN", "GITHUB_TOKEN")

    def device_client_id(self, cfg: AppSettings) -> str:
        return cfg.github_client_id

    async def identify(self, token: str) -> base.Identity:
        token = token.strip()
        if not token or any(c.isspace() for c in token):
            raise base.ConnectionProblem("That does not look like a GitHub token.")
        try:
            async with base.http_client() as client:
                reply = await client.get(f"{API}/user", headers=_headers(token))
        except httpx.HTTPError:
            raise base.ConnectionProblem(
                "Could not reach GitHub. Check this server's internet connection."
            ) from None
        if reply.status_code in (401, 403):
            raise base.ConnectionProblem(
                "GitHub rejected that token. Check that it is complete and has not expired."
            )
        if reply.status_code != 200:
            raise base.ConnectionProblem(f"GitHub answered with HTTP {reply.status_code}.")
        data = reply.json()
        login = str(data.get("login") or "")
        if not login:
            raise base.ConnectionProblem("GitHub did not say whose token this is.")
        return base.Identity(
            account=login,
            settings={
                "login": login,
                "id": data.get("id"),
                "name": _one_line(str(data.get("name") or "")),
                # only a classic token reports scopes; a fine-grained one leaves this empty
                "scopes": reply.headers.get("x-oauth-scopes", ""),
            },
        )

    async def check_config(self, token: str, config: dict[str, Any]) -> dict[str, Any]:
        repo = str(config.get("repo") or "").strip().removesuffix("/").removesuffix(".git")
        repo = repo.removeprefix("https://github.com/").removeprefix("github.com/")
        if not repo:
            return {}
        if not REPO.match(repo):
            raise base.ConnectionProblem("The repository is written owner/name, like octocat/hello-world.")
        try:
            async with base.http_client() as client:
                reply = await client.get(f"{API}/repos/{repo}", headers=_headers(token))
        except httpx.HTTPError:
            raise base.ConnectionProblem("Could not reach GitHub to check the repository.") from None
        if reply.status_code in (403, 404):
            raise base.ConnectionProblem(
                f"GitHub cannot find {repo} with this connection. Check the name, and that the token can see it."
            )
        if reply.status_code != 200:
            raise base.ConnectionProblem(f"GitHub answered with HTTP {reply.status_code}.")
        return {"repo": reply.json().get("full_name") or repo}  # GitHub's own spelling of the name

    def plain_env(self, settings: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
        env = {
            "GIT_TERMINAL_PROMPT": "0",  # a missing credential is an error, never a question nobody can answer
            "GH_PROMPT_DISABLED": "1",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "credential.https://github.com.helper",
            "GIT_CONFIG_VALUE_0": CREDENTIAL_HELPER,
        }
        login, user_id = settings.get("login"), settings.get("id")
        if login and user_id:
            name = _one_line(settings.get("name") or "") or login
            email = f"{user_id}+{login}@users.noreply.github.com"  # GitHub's address that attributes commits to the account
            env |= {
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_COMMITTER_NAME": name,
                "GIT_COMMITTER_EMAIL": email,
            }
        if repo := config.get("repo"):
            env["GH_REPO"] = repo
        return env

    def agent_note(self, account: str, config: dict[str, Any]) -> str:
        lines = [
            (
                f"GitHub: git and the gh command are signed in as @{account}. Use them for repositories, issues and "
                "pull requests. Clone with https URLs; credentials are already set up."
            )
        ]
        if repo := config.get("repo"):
            lines.append(f"This project's repository is {repo}: git clone https://github.com/{repo}.git")
        return "\n".join(lines)
