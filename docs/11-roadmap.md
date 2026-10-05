---
title: Roadmap
group: Reference
summary: What is built, what comes next and what is deliberately left for later.
---

# Roadmap

## Built

- Projects with an overview page and a task manager: **board**, **list** and **schedule timeline**.
- Tasks with custom properties, manual, one-off and recurring schedules and attempt history.
- An always-on **scheduler** with a concurrency limit, cancel, and recovery after restarts.
- **Cells** in Docker with a clear contract (`/workspace`, `/cell/input.json`, `/cell/result.md`).
- **Settings**: Docker connection, cell defaults, time zone, encrypted keys.
- **Codex agents**: tasks can run with a Codex agent in a cell, each run with its own private working folder.
- **Codex connection**: each user signs in with ChatGPT once; the login is encrypted and can be handed to a cell.
- **Invite only** access with requests, invite links and an administrator.
- **Installer**, `doctor`, systemd service and migrations.

## Next

1. **Shared folders.** Named folders a project defines (a drop-off, for example) that a task can mount read-only or
   read/write, so one task can hand files to the next. Runs that write to the same folder take turns.
2. **Agents.** A durable identity with instructions, a harness (for example Codex or Pi) and a model, run inside a
   cell. The cell contract is the starting point.
3. **Key injection.** Hand selected stored keys to cells, with redaction in logs. The Codex login already travels
   safely into cells and back; other keys still need the same path.
4. **Tasks from agents, webhooks and workflows**, using the same task path as everything else.
5. **Notifications and email.** Tell the administrator about new access requests, and tell people when work needs
   review or fails. Email the invite link.
6. **Live updates** instead of polling.
7. **Password reset.**
8. **Workflows.** A visual canvas that creates and updates tasks.
9. **Usage on the project overview.** AI usage per project, with tokens per model as horizontal bars and a day,
   week or month filter.

## Later

- Per-cell network control and per-agent cell profiles.
- Memory providers (run, agent, project and long-term memory).
- Running cells on more than one machine.

## Deliberately not planned yet

3D visualisation, a global command centre, elaborate multi-project orchestration, and billing or budget logic. They
become useful once real projects are running here.
