---
title: Getting started
group: Introduction
summary: From a fresh install to your first task running in a cell.
---

# Getting started

## 1. Install

On a Linux machine (a normal user with `sudo`), one command:

```bash
curl -fsSL https://github.com/RT-codes/ThemisForge/releases/latest/download/install.sh | sh
```

(On Windows 10 or 11, in PowerShell, not Command Prompt: `irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1 | iex`.)

It downloads the newest release, checks that Docker works (and offers to install it if it is missing), creates your
configuration and starts Themis as a service. Details and options are in [Install and operations](/docs/operations).

Just trying it on your own computer, or working on Themis itself? Clone the repository and run `./themis start` for a
development setup with hot reload, then open `http://localhost:5173`.

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
> A recurring task parked in **Backlog** is paused. Only tasks in **Ready** run on their schedule.

## Where to go next

- [Projects and tasks](/docs/tasks): statuses, custom properties, the board.
- [Scheduling](/docs/scheduling): one-off and repeating schedules, time zones.
- [Cells and workspaces](/docs/cells): what the container sees and where files end up.
