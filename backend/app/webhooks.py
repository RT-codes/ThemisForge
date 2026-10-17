"""Webhooks: an address another program can post to, to make a task in a project.

Who decides what. The sender decides only what its message says. Everything else about the task (the board and
status it lands in, what runs it, its properties, its schedule, its automation guard) is set on the webhook by the
project's owner, because a message from outside must never be able to choose how much work Themis does, with which
agent, or where. The message reaches the task through two templates, `{{path.to.value}}` holes filled from the message.

The address is the only secret (`/api/hooks/<token>`); a hash of it is stored, so it is shown once, when it is made.
Everything that arrives is written to the webhook's delivery log, kept short, with the message itself: knowing what the
other side really sent is the hard part of every webhook.
"""

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import boards
from .models import Project, Task, Webhook, WebhookDelivery, utcnow
from .properties import clean_values
from .schemas import TaskIn
from .tasks import TaskError, agent_for, new_task, workflows_for

MAX_BODY = 1024 * 1024  # a message bigger than this is not read
KEEP_PAYLOAD = 20_000  # characters of a message kept in the delivery log
KEEP_DELIVERIES = 50  # deliveries kept per webhook
RATE_LIMIT = 60  # messages per webhook per minute; a sender that must send more should batch them
TITLE_MAX = 200
DESCRIPTION_MAX = 20_000  # as TaskIn

# The names senders give their event and delivery id. The first one present is used: GitHub, GitLab, Bitbucket.
EVENT_HEADERS = ("x-github-event", "x-gitlab-event", "x-event-key")
DELIVERY_HEADERS = ("x-github-delivery", "x-gitlab-event-uuid", "idempotency-key")

_HOLE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_hits: dict[int, deque[float]] = {}


# the address


def too_many(webhook_id: int) -> bool:
    """Count this message against the webhook's minute. In memory: one server process does everything, and a restart
    forgetting the count is harmless."""
    now = time.monotonic()
    hits = _hits.setdefault(webhook_id, deque())
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        return True
    hits.append(now)
    return False


# reading a message


@dataclass
class Message:
    raw: str  # as it came
    data: Any  # what it parsed to (JSON, or a form), None when it was plain text
    event: str  # what the sender called it, "" when it did not say
    key: str  # the sender's id for this delivery, "" when it did not give one


def read(raw: bytes, content_type: str, headers: dict[str, str]) -> Message:
    """A message as JSON or as a form. GitHub's default is a form with the JSON in a `payload` field, so that is
    understood too; anything else is plain text, which the templates reach as {{_raw}}."""
    text = raw.decode(errors="replace")
    data: Any = None
    kind = content_type.lower()
    if "x-www-form-urlencoded" in kind:
        form = parse_qs(text, keep_blank_values=True)
        data = {k: v[0] if len(v) == 1 else v for k, v in form.items()}
        if isinstance(data.get("payload"), str):
            data = _json(data["payload"]) or data
    elif "json" in kind or text.lstrip().startswith(("{", "[")):
        data = _json(text)
    event = next((headers[h] for h in EVENT_HEADERS if headers.get(h)), "")
    key = next((headers[h] for h in DELIVERY_HEADERS if headers.get(h)), "")
    return Message(text, data, event[:60], key[:120])


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def lookup(message: Message, path: str) -> str:
    """The value at a path like `issue.user.login` or `commits.0.message`, as text; empty when it is not there. `_raw` is
    the whole message and `_event` what the sender called it."""
    if path == "_raw":
        return message.raw
    if path == "_event":
        return message.event
    value = message.data
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return ""
    return _text(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False)  # an object or a list: the agent can read JSON


def render(template: str, message: Message) -> str:
    return _HOLE.sub(lambda m: lookup(message, m.group(1)), template)


def unmatched(rules: list[dict[str, Any]], message: Message) -> str:
    """Why the message makes no task, or "" when every rule matches. A rule names a value and what it may be; with
    nothing listed it only asks that the value is there."""
    for rule in rules:
        value = lookup(message, rule["path"])
        wanted = rule.get("equals") or []
        if wanted and value not in wanted:
            return f"{rule['path']} is '{value[:60]}', not {' or '.join(repr(w) for w in wanted)}"
        if not wanted and not value:
            return f"{rule['path']} is missing"
    return ""


def title_of(webhook: Webhook, message: Message) -> str:
    """The template's, else the message's own "title", else the webhook's name. One line, as a title is."""
    if webhook.title_template:
        text = render(webhook.title_template, message)
    else:
        text = lookup(message, "title")
    return " ".join(text.split())[:TITLE_MAX] or webhook.name


def description_of(webhook: Webhook, message: Message) -> str:
    """The template's, else the message's own "description", else the message itself, so nothing that arrived is lost."""
    if webhook.description_template:
        text = render(webhook.description_template, message)
    elif description := lookup(message, "description"):
        text = description
    elif isinstance(message.data, dict | list):
        text = json.dumps(message.data, ensure_ascii=False, indent=2)
    else:
        text = message.raw
    return text[:DESCRIPTION_MAX]


# making the task


def task_for(webhook: Webhook, title: str, description: str) -> TaskIn:
    """The task this webhook makes: the message supplies the two texts, the webhook everything else. A schedule and the
    automation guard are not offered at all, so a message can only ever make a task that runs once, when its status says."""
    return TaskIn(
        title=title,
        description=description,
        status=webhook.status,
        board_id=webhook.board_id,
        properties=webhook.properties,
        review_on_success=webhook.review_on_success,
        harness=webhook.harness,  # type: ignore[arg-type]
        workflow_ids=webhook.workflow_ids,
        agent_id=webhook.agent_id,
    )


async def problem(session: AsyncSession, webhook: Webhook) -> str:
    """Why a message would be refused right now, or "". The same checks that making the task runs, so a board that was
    deleted or a status that is gone shows on the webhook before the first message finds out."""
    if webhook.board_id is None:
        return "Its board was deleted. Choose another."
    project = await session.get_one(Project, webhook.project_id)
    try:
        body = task_for(webhook, "x", "")
        board = await boards.project_board(session, project.id, webhook.board_id)
        boards.check_status(board, body.status)
        clean_values(project.properties, body.properties)
        if body.agent_id is not None:
            await agent_for(session, project.id, body.agent_id)
        else:
            await workflows_for(session, project.id, body.harness, body.workflow_ids)
    except (ValidationError, boards.BoardError, TaskError, ValueError) as e:
        return _reason(e)
    return ""


def _reason(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
    return str(e)


@dataclass
class Result:
    status_code: int
    outcome: str  # as WebhookDelivery.outcome
    detail: str = ""
    task: Task | None = None


async def receive(
    session: AsyncSession, webhook: Webhook, raw: bytes, content_type: str, headers: dict[str, str]
) -> Result:
    """One message arrives: make the task it asks for, or say why not. The outcome is always written to the delivery
    log, whatever it is. The caller wakes the scheduler when the task is Ready."""
    message = read(raw, content_type, headers)
    webhook_id = webhook.id
    result = await _decide(session, webhook, message)
    if result.task is None:
        await session.rollback()  # whatever a refused attempt left in the session is not wanted
        webhook = await session.get_one(Webhook, webhook_id)
    webhook.last_received_at = utcnow()
    session.add(
        WebhookDelivery(
            webhook_id=webhook_id,
            outcome=result.outcome,
            detail=result.detail[:300],
            task_id=result.task.id if result.task else None,
            event=message.event,
            delivery_key=message.key,
            payload=message.raw[:KEEP_PAYLOAD],
        )
    )
    await session.flush()
    await _prune(session, webhook_id)
    await session.commit()
    return result


async def _decide(session: AsyncSession, webhook: Webhook, message: Message) -> Result:
    if not webhook.enabled:
        return Result(409, "refused", "This webhook is switched off")
    if webhook.board_id is None:
        return Result(409, "refused", "Its board was deleted. Choose another in the webhook's settings.")
    if (
        message.event == "ping"
    ):  # what GitHub sends when a webhook is made: it only checks that someone answers
        return Result(200, "skipped", "A ping: the webhook works")
    if message.key and await session.scalar(
        select(WebhookDelivery.id).where(
            WebhookDelivery.webhook_id == webhook.id,
            WebhookDelivery.delivery_key == message.key,
            WebhookDelivery.outcome == "created",
        )
    ):
        return Result(200, "duplicate", "Already received: the sender sent this delivery again")
    if why := unmatched(webhook.rules, message):
        return Result(200, "skipped", f"No task: {why}")
    project = await session.get_one(Project, webhook.project_id)
    try:
        body = task_for(webhook, title_of(webhook, message), description_of(webhook, message))
        task = await new_task(session, project, body, f"Webhook {webhook.name}", f"webhook:{webhook.id}")
    except (ValidationError, TaskError) as e:
        return Result(422, "refused", _reason(e))
    return Result(201, "created", task=task)


async def _prune(session: AsyncSession, webhook_id: int) -> None:
    """Keep the newest deliveries; the log is for the last few things that went wrong, not for the record."""
    count = await session.scalar(
        select(func.count()).select_from(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)
    )
    if count and count > KEEP_DELIVERIES:
        oldest = (
            select(WebhookDelivery.id)
            .where(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.id.desc())
            .offset(KEEP_DELIVERIES)
        )
        await session.execute(delete(WebhookDelivery).where(WebhookDelivery.id.in_(oldest)))
