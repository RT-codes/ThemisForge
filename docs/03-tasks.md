---
title: Projects and tasks
group: Using ThemisForge
summary: The project dashboard, task statuses, custom properties and the board.
---

# Projects and tasks

## The project dashboard

Every project opens as a dashboard with a header and three views of the **same** tasks:

- **Board**: columns by status, with drag and drop.
- **List**: a table, handy when there are many tasks.
- **Schedule**: a timeline of what will run in the next 24 hours or 7 days.

The header shows how many tasks are running, ready, waiting for review or failed, when the next run is due, and
whether the scheduler is on and how many cells are busy.

## Statuses

| Status | Meaning |
| --- | --- |
| **Inbox** | Not scheduled yet. A recurring task parked here is **paused**. |
| **Ready** | The scheduler may pick it up. With no schedule it runs as soon as a cell is free; with a schedule it runs when due. |
| **Running** | A cell is working on it right now. |
| **Review** | Finished and waiting for a human. |
| **Done** | Finished. |
| **Blocked** | Waiting on something, or cancelled while running. |
| **Failed** | The last attempt failed. |

Only the scheduler moves a task into **Running**. You start a task by making it Ready or by pressing **Run now**.

## What happens when an attempt ends

| Task type | Succeeded | Failed | Cancelled |
| --- | --- | --- | --- |
| **One-off or manual** | Done (or Review, see below) | Failed | Blocked |
| **Recurring** | Back to Ready, next occurrence computed | Back to Ready, failure recorded | Back to Ready |

A recurring task whose last attempt failed shows a small warning marker on its card, and the failed attempt stays in
its history. The next occurrence still happens.

## Task options

- **Title and description**: what needs doing. The description is passed to the cell.
- **Status**: where the task is in its life.
- **Schedule**: manual, once, or recurring. See [Scheduling](/docs/scheduling).
- **Ask for review when it succeeds**: one-off tasks end in **Review** instead of **Done**, so a human looks at the
  result first.
- **Properties**: your own fields, see below.

## Custom properties

Each project defines its own fields. Open the project menu (the three dots) and choose **Task properties**.

| Type | Use it for |
| --- | --- |
| **Text** | Free text such as an owner or a link. |
| **Number** | Cost, effort, a score. |
| **Select** | A fixed set of options such as Priority: Low, Medium, High. |
| **Checkbox** | A yes or no flag. |
| **Date** | A due date or a deadline. |

Properties show on the cards, in the list as columns, and are passed to the cell with the task. Removing a property
hides its values.

## Moving tasks

Drag a card to another column or to a new place in a column. A few rules keep things honest:

- You cannot drop a task into **Running**, and a running card cannot be dragged. Only the scheduler starts tasks.
- A running task cannot be edited or deleted. Press **Cancel run** first.
- Moving a task to **Ready** makes it eligible to run. For a task with no schedule that means *now*.

## Run now, cancel and delete

Open a task to find the actions:

- **Run now**: makes the task Ready and wakes the scheduler. A recurring task still keeps its normal schedule afterwards.
- **Cancel run**: stops the cell. The attempt is recorded as cancelled.
- **Delete**: removes the task and its history. Files it wrote to the project workspace are not touched.

## Attempts and history

The **History** tab of a task lists every attempt with its status, start time and duration. Select one to see its
**result** and its full **log**. While a task is running the log updates live.
