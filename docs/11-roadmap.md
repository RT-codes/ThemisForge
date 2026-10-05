---
title: Roadmap
group: Reference
summary: What is built, what comes next and what is deliberately left for later.
---

# Roadmap

## Built

- Projects with a dashboard: **board**, **list** and **schedule timeline**.
- Tasks with custom properties, manual, one-off and recurring schedules and attempt history.
- An always-on **scheduler** with a concurrency limit, cancel, and recovery after restarts.
- **Cells** in Docker with a clear contract (`/workspace`, `/cell/input.json`, `/cell/result.md`).
- **Settings**: Docker connection, cell defaults, time zone, encrypted keys.
- **Invite only** access with requests, invite links and an administrator.
- **Installer**, `doctor`, systemd service and migrations.

## Next

1. **Agents.** A durable identity with instructions, a harness (for example Codex or Pi) and a model, run inside a
   cell. The cell contract is the starting point.
2. **Key injection.** Hand selected stored keys to cells, with redaction in logs.
3. **Tasks from agents, webhooks and workflows**, using the same task path as everything else.
4. **Notifications and email.** Tell the administrator about new access requests, and tell people when work needs
   review or fails. Email the invite link.
5. **Live updates** instead of polling.
6. **Password reset.**
7. **Workflows.** A visual canvas that creates and updates tasks.

## Later

- Per-cell network control and per-agent cell profiles.
- Memory providers (run, agent, project and long-term memory).
- Running cells on more than one machine.

## Deliberately not planned yet

3D visualisation, a global command centre, elaborate multi-project orchestration, and billing or budget logic. They
become useful once real projects are running here.
