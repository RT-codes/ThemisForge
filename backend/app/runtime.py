"""Capabilities shared operations need from the running application.

FastAPI's app.state supplies these attributes. Keeping this structural interface
separate lets MCP and background callers use operations without an HTTP request.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.execution.scheduler import Scheduler
    from app.features.connections.codex import CodexLogins
    from app.features.connections.service import DeviceLogins
    from app.features.system.preflight import Preflight
    from app.features.system.runlog import Trail
    from app.features.system.updates import UpdateChecker
    from app.features.tools.auth import McpLogins
    from app.features.workflows.runner import WorkflowRunner


class Runtime(Protocol):
    scheduler: "Scheduler"
    workflows: "WorkflowRunner"
    codex_logins: "CodexLogins"
    device_logins: "DeviceLogins"
    mcp_logins: "McpLogins"
    preflight: "Preflight"
    trail: "Trail"
    updates: "UpdateChecker"
