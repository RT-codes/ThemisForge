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
- **Connections**: a searchable list in Settings to connect services once, by token or by signing in with a code. GitHub
  is the first; a project chooses one connection per service and each agent opts in to it.
- **Resource budget**: all running cells together use at most a number of CPUs and an amount of memory, with the machine's
  real size and a recommendation shown in Settings.
- **Shared folders**: a `shared` folder in every project plus managed and host folders, read only or read and write,
  with optional turn taking, and administrator approved mount roots for host folders.
- **Agents**: a name, role, instructions, harness, model, cell and folders per agent, an editor page for them, and
  an agent picker on tasks and workflow Agent nodes.
- **Skills, tools and keys**: SKILL.md skills, MCP tool servers and stored keys given to an agent, with log redaction and a check
  that a tool's command exists in the agent's image.
- **Folder nodes in workflows**: a Folder node joined to an Agent node hands that agent a shared folder for the step, with
  lines the run does not treat as steps.
- **Cell profiles**: the cell size layered from Settings, to the project, to the agent, to a single workflow step.
- **Invite only** access with requests, invite links and an administrator.
- **Update notice**: administrators are told when a newer release exists, with a daily check that can be switched off.
- **Install and upgrade** with one command on Linux and Windows (`themis install`, `themis upgrade` with a backup and an automatic rollback), `doctor` with a trail of recent runs, a systemd service and migrations.

## Next

1. **Tasks from agents, webhooks and workflows**, using the same task path as everything else.
2. **Notifications and email.** Tell the administrator about new access requests, and tell people when work needs
   review or fails. Email the invite link.
3. **Live updates** instead of polling.
4. **Password reset.**
5. **Usage on the project overview.** AI usage per project, with tokens per model as horizontal bars and a day,
   week or month filter.
6. **Windows, proven on real computers.** Windows 10 and 11 install with one command and pass the automated tests, but have been run on far fewer real machines than Linux. Next: a Windows service that starts before anyone logs in, and macOS.
7. **More agent engines.** Codex is the one supported today; Claude and OpenRouter are next.

## Later

- Per-cell network control.
- An API cost budget next to the hardware budget, spent by tasks and projects.
- Memory providers (run, agent, project and long-term memory).
- Running cells on more than one machine.

## Deliberately not planned yet

3D visualisation, a global command centre, elaborate multi-project orchestration, and billing or budget logic. They
become useful once real projects are running here.
