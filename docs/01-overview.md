---
title: What is ThemisForge
group: Introduction
summary: A self-hosted harness that runs agent work around the clock, organised into projects and tasks.
---

# What is ThemisForge

ThemisForge is a **self-hosted control room for agent projects**. You describe work as *tasks*, give them
schedules, and an always-on scheduler runs them for you, day and night, each one inside a fresh, isolated
container.

It runs on a machine you own (a small VM is plenty) and is operated from the browser.

## The big idea

- A **project** is one agentic system. You open it from the sidebar and it becomes a dashboard.
- A **task** is a unit of work. It can be manual, run once at a set time, or repeat on a schedule.
- An always-on **scheduler** picks up tasks that are due and starts a **cell** for each one.
- A **cell** is a throwaway Docker container. It is created for the task, does the work, and is removed.

Nothing here depends on you being logged in. Close the browser and the schedule keeps running.

## The four things to know

| Concept | What it is |
| --- | --- |
| **Project** | The container for one system: its tasks, schedule and workspace folder. |
| **Task** | A durable piece of work with a status, an optional schedule and your own custom properties. |
| **Attempt** | One execution of a task. A recurring task has many attempts, each with its own log and result. |
| **Cell** | The short-lived container an attempt runs in. Created per attempt, removed afterwards. |

## How a task moves

<div class="docs-flow">
<span class="node muted">Inbox</span><span class="arrow">&rarr;</span><span class="node sky">Ready</span><span class="arrow">&rarr;</span><span class="node amber">Running</span><span class="arrow">&rarr;</span><span class="node violet">Review</span><span class="arrow">&rarr;</span><span class="node green">Done</span>
</div>
<div class="docs-flow small">
<span class="label">If an attempt does not succeed, a one-off task ends as</span><span class="node red">Failed</span><span class="label">or</span><span class="node yellow">Blocked</span><span class="label">(cancelled)</span>
</div>

You decide when a task is **Ready**. From then on the scheduler is in charge: when it is due and a cell is free, it
runs. Recurring tasks return to Ready after every attempt, ready for the next occurrence.
See [Projects and tasks](/docs/tasks) and [Scheduling](/docs/scheduling).

## What works today, and what is next

ThemisForge currently runs a **placeholder program** inside each cell: it reads the task, prints it, and writes a
result file. That is deliberate. The whole pipeline (projects, boards, schedules, cells, logs, results, access
control, installation) is in place, and agent harnesses plug into exactly that spot.

Agents, workflows and key injection are the next steps. See the [roadmap](/docs/roadmap).

> [!TIP]
> New here? Go to [Getting started](/docs/getting-started). It takes about five minutes.
