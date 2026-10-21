from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse

import app.control.routes as control
import app.features.agents.routes as agents
import app.features.agents.skill_routes as skills
import app.features.connections.codex_routes as codex
import app.features.connections.routes as connections
import app.features.identity.access_routes as access
import app.features.identity.auth_routes as auth
import app.features.notifications.routes as notifications
import app.features.projects.routes as projects
import app.features.projects.workspace_routes as workspaces
import app.features.storage.routes as volumes
import app.features.system.routes as system
import app.features.tasks.routes as tasks
import app.features.tools.auth_routes as mcp_auth
import app.features.tools.routes as tools
import app.features.webhooks.routes as webhooks
import app.features.workflows.routes as workflows
from app.api.frontend import mount_frontend
from app.bootstrap import configure_runtime, lifespan
from app.control.server import ControlEndpoint
from app.errors import ApplicationError
from app.features.system.version import build_info
from app.features.tasks.creation import TaskError

# The interactive API reference lives under /api so that /docs is the user documentation (a frontend page).
app = FastAPI(
    title="Themis",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


@app.exception_handler(TaskError)
async def task_error(_: Request, e: TaskError) -> JSONResponse:
    """A task that cannot be made or changed like that (see tasks.py) is a request that cannot be right."""
    return JSONResponse({"detail": str(e)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


@app.exception_handler(ApplicationError)
async def application_error(_: Request, e: ApplicationError) -> JSONResponse:
    return JSONResponse({"detail": e.detail}, status_code=e.status_code, headers=e.headers)


configure_runtime(app)


api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(access.router)
api.include_router(projects.router)
api.include_router(tasks.router)
api.include_router(workspaces.router)
api.include_router(system.router)
api.include_router(codex.router)
api.include_router(connections.router)
api.include_router(workflows.router)
api.include_router(volumes.router)
api.include_router(agents.router)
api.include_router(skills.router)
api.include_router(tools.router)
api.include_router(mcp_auth.router)
api.include_router(notifications.router)
api.include_router(webhooks.router)
api.include_router(control.router)
api.include_router(webhooks.receiver)


@api.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": build_info().version}


@api.get("/version")
async def version() -> dict[str, str]:
    """Which Themis this is (public, like /health): the release number, the commit it was built from and whether it is a
    release bundle or a git checkout."""
    return build_info().to_dict()


app.include_router(api)
# MCP, for agents outside Themis. Before the frontend's catch-all below, which would answer a GET with the web page.
app.add_route("/mcp", ControlEndpoint(), methods=["GET", "POST", "DELETE"], include_in_schema=False)

mount_frontend(app)
