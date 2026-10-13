"""Signing in to tool servers (MCP) that ask people to. Tokens for runs, kept fresh, never shown.

How it is laid out, so a change goes to the right place:

- scheme.py   what a way of signing in must do (the interface), the errors, and the list of known ways. A new way of
              signing in (another OAuth flavour, an API key with its own header) is a class here plus an entry in
              SCHEMES; nothing else in Themis changes.
- oauth.py    the standard way MCP servers sign people in (the only scheme so far).
- profiles.py + servers.yaml
              what one server does differently from the standard, as data.
- logins.py   the stored sign ins: starting and finishing one, a token for a run, renewing under a lock, keep alive.

The numbers (how early to renew, how long a token is assumed to last, how long a sign in waits) are
AppSettings.mcp_auth, edited in Settings. The page routes are app/routers/mcp_auth.py; a tool opts in with
`auth: oauth` (app/mcp.py), and the run takes the token in app/scheduler.py.
"""

from .logins import ACTIVE, NEEDS_SIGN_IN, Completed, McpLogins, login_for, unseal
from .scheme import (
    SCHEMES,
    AuthProblem,
    AuthScheme,
    Context,
    SignInRequired,
    detect,
    get_scheme,
    resource_key,
)

__all__ = [
    "ACTIVE",
    "NEEDS_SIGN_IN",
    "SCHEMES",
    "AuthProblem",
    "AuthScheme",
    "Completed",
    "Context",
    "McpLogins",
    "SignInRequired",
    "detect",
    "get_scheme",
    "login_for",
    "resource_key",
    "unseal",
]
