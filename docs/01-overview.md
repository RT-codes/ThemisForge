---
title: What is Themis
group: Introduction
summary: A self-hosted harness that runs agent work around the clock, organised into projects and tasks.
---

# What is Themis

Themis is a **self-hosted control room for agent projects**. You describe work as *tasks*, give them
schedules, and an always-on scheduler runs them for you, day and night, each one inside a fresh, isolated
container.

It runs on a machine you own (a small VM is plenty) and is operated from the browser.

## The big idea

- A **project** is one agentic system. You open it from the sidebar to see its overview, with the task manager as a sub page.
- A **task** is a unit of work. It can be manual, run once at a set time, or repeat on a schedule.
- An always-on **scheduler** picks up tasks that are due and starts a **cell** for each one.
- A **cell** is a throwaway Docker container. It is created for the task, does the work, and is removed.

Nothing here depends on you being logged in. Close the browser and the schedule keeps running.

## The things to know

| Concept | What it is |
| --- | --- |
| **Project** | The container for one system: its tasks, schedule, agents and shared folders. |
| **Workspace** | A named area of a project, such as research or publishing. It holds one or more boards. A new project has one, called Main. |
| **Board** | A Kanban with its own statuses. A workspace can hold several; every task lives on one board. |
| **Task** | A durable piece of work with a status, an optional schedule and your own custom properties. |
| **Agent** | A configured worker of a project: a role, instructions, a model and the skills, tools, keys and folders it may use. See [Agents](/docs/agents). |
| **Workflow** | A flowchart of steps (tasks, agents, conditions, branches) that a task can play. See [Workflows](/docs/workflows). |
| **Webhook** | An address other programs send messages to; each message makes a task. See [Webhooks](/docs/webhooks). |
| **Notification** | A chat (Discord today) a project sends a message to when a task fails or something waits for you. See [Notifications](/docs/notifications). |
| **Attempt** | One execution of a task. A recurring task has many attempts, each with its own log and result. |
| **Cell** | The short-lived container an attempt runs in. Created per attempt, removed afterwards. |

## How a task moves

<div class="docs-flow">
<span class="node muted">Backlog</span><span class="arrow">&rarr;</span><span class="node sky">Ready</span><span class="arrow">&rarr;</span><span class="node amber">Running</span><span class="arrow">&rarr;</span><span class="node violet">Review</span><span class="arrow">&rarr;</span><span class="node green">Done</span>
</div>
<div class="docs-flow small">
<span class="label">If an attempt does not succeed, a one-off task ends as</span><span class="node red">Failed</span><span class="label">or</span><span class="node yellow">Blocked</span><span class="label">(cancelled)</span>
</div>

You decide when a task is **Ready**. From then on the scheduler is in charge: when it is due and a cell is free, it
runs. Recurring tasks return to Ready after every attempt, ready for the next occurrence.
See [Projects and tasks](/docs/tasks) and [Scheduling](/docs/scheduling).

## What works today, and what is next

A task can be done by an **agent**: a role and instructions, run by **Codex** or **Claude Code** inside the cell, in a private working
folder, with the skills, tools and keys you gave it. Tasks can be chained into **workflows** (a flowchart where one
agent's result feeds the next step), and agents hand files to each other through shared folders. See
[Agents](/docs/agents), [Workflows](/docs/workflows), [Codex](/docs/codex) and [Claude Code](/docs/claude-code).

A task with no agent runs a small **placeholder program** instead: it reads the task, prints it, and writes a result
file. It needs nothing installed, which makes it a quick way to try the board, the schedule and the cells.

More agent engines (Claude and OpenRouter) are next. See the [roadmap](/docs/roadmap).

> [!TIP]
> New here? Go to [Getting started](/docs/getting-started). It takes about five minutes.
