"""Register every mapped table on the shared Base, including for Alembic."""

from app.persistence.models.automation import NotificationTarget, Webhook, WebhookDelivery
from app.persistence.models.common import (
    AttemptStatus,
    NodeStatus,
    RequestStatus,
    RunStatus,
    ScheduleKind,
    TaskStatus,
    UtcDateTime,
    utcnow,
)
from app.persistence.models.configuration import Agent, AppSetting, McpServer, Secret, Volume
from app.persistence.models.connections import CodexConnection, Connection, McpLogin, ProjectConnection
from app.persistence.models.identity import AccessRequest, ControlToken, Invite, User
from app.persistence.models.projects import Board, BoardStatus, Project, ProjectEvent, Workspace
from app.persistence.models.tasks import Attempt, Task, TaskStage
from app.persistence.models.workflows import NodePreset, Workflow, WorkflowNodeRun, WorkflowRun

__all__ = [
    "AccessRequest",
    "Agent",
    "AppSetting",
    "Attempt",
    "AttemptStatus",
    "Board",
    "BoardStatus",
    "CodexConnection",
    "Connection",
    "ControlToken",
    "Invite",
    "McpLogin",
    "McpServer",
    "NodePreset",
    "NodeStatus",
    "NotificationTarget",
    "Project",
    "ProjectConnection",
    "ProjectEvent",
    "RequestStatus",
    "RunStatus",
    "ScheduleKind",
    "Secret",
    "Task",
    "TaskStage",
    "TaskStatus",
    "User",
    "UtcDateTime",
    "Volume",
    "Webhook",
    "WebhookDelivery",
    "Workflow",
    "WorkflowNodeRun",
    "WorkflowRun",
    "Workspace",
    "utcnow",
]
