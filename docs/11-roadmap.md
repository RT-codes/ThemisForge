---
title: Roadmap
group: Reference
summary: What is built, what comes next and what is deliberately left for later.
---

# Roadmap

## Built

- Projects with an overview page and a task manager: **board**, **list** and **schedule timeline**.
- Tasks with custom properties, manual, one-off and recurring schedules and attempt history.
- An always-on **scheduler** that hands out a CPU and memory **budget** to cells, with cancel and recovery after restarts.
- **Cells** in Docker with a clear contract (`/workspace`, `/cell/input.json`, `/cell/result.md`).
- **Settings**: Docker connection, cell defaults, time zone, encrypted keys.
- **Workflow editor**: nodes, a Test run, and a history of runs with the log of every node.
- **Codex agents**: tasks can run with a Codex agent in a cell, each run with its own private working folder.
- **Codex connection**: each user signs in with ChatGPT once; the login is encrypted and can be handed to a cell.
- **Resource budget**: all running cells together use at most a number of CPUs and an amount of memory, with the machine's
  real size and a recommendation shown in Settings.
- **Shared folders**: a `shared` folder in every project plus managed and host folders, read only or read and write,
  with optional turn taking, and administrator approved mount roots for host folders.
- **Agents**: a name, role, instructions, harness, model, cell and folders per agent, an editor page for them, and
  an agent picker on tasks and workflow Agent nodes.
- **Cell profiles**: the cell size layered from Settings, to the project, to the agent, to a single workflow step.
- **Invite only** access with requests, invite links and an administrator.
- **Installer**, `doctor`, systemd service and migrations.

## Next

1. **Skills, tools and keys for agents.** Skills and MCP servers an agent can use, and stored keys handed to its cell
   with redaction in logs. The Codex login already travels safely into cells and back; other keys still need the
   same path.
2. **Folders in the workflow canvas.** Folder nodes you connect to an Agent node, instead of picking them in its panel.
3. **Tasks from agents, webhooks and workflows**, using the same task path as everything else.
4. **Notifications and email.** Tell the administrator about new access requests, and tell people when work needs
   review or fails. Email the invite link.
5. **Live updates** instead of polling.
6. **Password reset.**
7. **Usage on the project overview.** AI usage per project, with tokens per model as horizontal bars and a day,
   week or month filter.

## Later

- Per-cell network control.
- An API cost budget next to the hardware budget, spent by tasks and projects.
- Memory providers (run, agent, project and long-term memory).
- Running cells on more than one machine.

## Deliberately not planned yet

3D visualisation, a global command centre, elaborate multi-project orchestration, and billing or budget logic. They
become useful once real projects are running here.
