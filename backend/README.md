# Backend organization

The backend remains one FastAPI application, one scheduler process and one shared
SQLAlchemy model registry. `app.main:app`, `python -m app.run`, and
`python -m app.doctor` are the stable entry points.

## Where responsibilities live

| Package | Responsibility |
| --- | --- |
| `app/main.py` | HTTP/MCP route registration and application error responses |
| `app/bootstrap.py` | Runtime construction and ordered startup/shutdown |
| `app/api/` | HTTP dependencies, session cookies and SPA serving |
| `app/features/` | Feature-owned schemas, operations, queries, rules and HTTP routes |
| `app/execution/` | Scheduling, planning, admission, attempt execution, cells and harnesses |
| `app/control/` | Incoming MCP transport, token reach and tool scopes |
| `app/persistence/` | Sessions, mapped models and migration runner |
| `app/config.py` | Environment/bootstrap settings and filesystem roots |
| `app/security.py`, `app/crypto.py` | Authentication and encryption primitives |

Features are grouped by what a person works with: identity, projects, tasks,
agents, workflows, connections, tools, storage, project configuration,
notifications, webhooks and system settings/status.

Inside a feature, `routes.py` translates HTTP requests into calls to operations.
`service.py` (or a specifically named operation module) owns mutations;
`queries.py` owns substantial read projections; `schemas.py` owns validated
inputs and outputs. Small features need fewer files. REST and MCP invoke the same
operations. Operations accept ordinary sessions, users and explicit runtime
capabilities, without constructing web requests or depending on controllers.

The `Runtime` protocol describes the capabilities supplied by the existing
application state. It does not introduce a separate container or service locator.
`ApplicationError` carries the existing error status/detail to both adapters;
application operations enforce ownership and administrator requirements.

## Execution boundaries

- `Scheduler` selects due work, opens attempts in one transaction and launches
  them after commit. Its public status/cancellation interface stays centralized.
- `RunPlanner` resolves agents, profiles, capabilities, mounts, connections and
  prompts into run plans and cell specifications.
- `ActiveRuns` owns live runs, starting reservations and renaming exclusions.
  Starting reservations cover the interval between choosing folders and launching
  committed attempts. These collections must never be independently duplicated.
- `AttemptExecutor` keeps credential leases, secret redaction, provider retries,
  output collection and finalization in their existing order.
- `cells/contract.py` defines the cell boundary; `docker.py` and `fake.py`
  implement it. Filesystem staging and credential writeback are separate helpers.
- `harnesses/` separates shared types, catalog/prompt rules, output rendering,
  provider scripts and the small harness dispatcher.

The workflow `runner.py` owns traversal, run recovery, cancellation and records.
`walk.py` remains the pure graph state machine. `triggers.py` observes flushes,
discards rolled-back moves and fires only after successful commit. `nodes.py`
owns node behavior; `approvals.py` owns persistent decisions and wakeups;
`folders.py` owns branch copies/merges and their hidden attempts.

## Data and lifecycle invariants

Project configuration files remain authoritative. `project_config/formats.py`
parses/renders their formats, `references.py` resolves names and permissions, and
`store.py` coordinates atomic writes and synchronization under the shared lock.
Database rows retain their identities and last valid parsed configuration.

`persistence/models/__init__.py` imports every mapped class onto the same `Base`.
Alembic imports that registration module. Moving model definitions does not
require a schema migration; table names, constraints, indexes and relationships
must remain unchanged.

Startup order remains: migrations, configuration sync, preflight, workflow
reconciliation, scheduler start/recovery, parked workflow resumption, MCP
transport, then the preflight watcher. Shutdown closes MCP, workflows, scheduler
and login coordinators before ending the run trail.

## Maintaining the boundaries

Shared operations and execution code must not import HTTP controllers. MCP tools
must not call routes. Persistence must not depend on features or transports.
`tests/test_architecture.py` checks these rules; `tests/test_runtime_order.py`
protects reservation, commit/rollback and lifecycle order.

Keep functions for ordinary stateless operations. Use objects when a component
owns lifecycle, concurrency or mutable state. Add a repository or interface only
for a concrete boundary, rather than creating one per database table.

Run checks from `backend/`:

```bash
uv run pytest
uv run ruff check . ../scripts --config pyproject.toml
uv run ruff format --check . ../scripts --config pyproject.toml
```
