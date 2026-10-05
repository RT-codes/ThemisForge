---
title: Getting started
group: Introduction
summary: From a fresh install to your first task running in a cell.
---

# Getting started

## 1. Install

On a Debian or Ubuntu machine:

```bash
git clone https://github.com/RT-codes/ThemisForge.git
cd ThemisForge
./themis install
```

This installs what is missing (Docker, uv, Node), builds the app, creates your configuration and starts ThemisForge
as a service. Details and options are in [Install and operations](/docs/operations).

Just trying it on your own computer? Run `./themis start` instead for a development setup with hot reload, then open
`http://localhost:5173`.

## 2. Create the administrator account

Open the address the installer printed (by default `http://127.0.0.1:8000`). The very first screen asks you to create
the **administrator** account. Everyone else joins later by invitation, see [Access and accounts](/docs/access).

## 3. Check Docker

Open **Settings** in the sidebar. The Docker card should say *Connected to Docker*. If it does not, the message tells
you what to fix, and [Troubleshooting](/docs/troubleshooting) has the common cases.

## 4. Create a project

Click **+** next to *Projects* in the sidebar, give it a name and optionally a description. You land on the project
dashboard.

## 5. Add a task and run it

1. Click **New task**, enter a title such as *Say hello*, and create it.
2. Open the task and press **Run now**.
3. The card moves to **Running**, then to **Done**.
4. Open the task again and look at the **History** tab: you see the log and the result of that attempt.

You have just run work in a cell.

## 6. Schedule it

Open the task, switch **Schedule** to *Recurring*, pick *Every hour* (or any other preset), save, and move the task to
**Ready**. Open the **Schedule** tab of the project to see the upcoming runs on a timeline.

> [!NOTE]
> A recurring task parked in **Inbox** is paused. Only tasks in **Ready** run on their schedule.

## Where to go next

- [Projects and tasks](/docs/tasks): statuses, custom properties, the board.
- [Scheduling](/docs/scheduling): one-off and cron schedules, time zones.
- [Cells and workspaces](/docs/cells): what the container sees and where files end up.
