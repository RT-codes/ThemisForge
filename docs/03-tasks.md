---
title: Projects and tasks
group: Using Themis
summary: The project dashboard, task statuses, custom properties and the board.
---

# Projects and tasks

## The project pages

Selecting a project in the sidebar opens its **Overview** and expands its sub pages. The overview shows how many
tasks are ready and running, and how many are scheduled for today and the next 7 days. **Tasks** (at
`/projects/<id>/tasks`) is the task manager, with a header and four views of the **same** tasks:

- **Board**: columns by status, with drag and drop.
- **List**: a table, handy when there are many tasks.
- **Schedule**: a timeline of what will run in the next 24 hours or 7 days.
- **History**: what was done on this board: tasks created, moved, sent or deleted, and changes to its statuses.

The header shows how many tasks are running, ready, waiting for review or failed, when the next run is due, and
whether the scheduler is on and how many cells are busy.

## Workspaces and boards

A project starts with one board, and the Tasks page is that board. When one board is not enough, for example because
research, building and publishing have different steps, you can split the work up:

- A **board** is one Kanban with its own [statuses](#your-own-statuses). Every task lives on exactly one board.
  Open the **...** menu on the Tasks page for **New board**, **Edit this board**, **Duplicate this board** (the same
  statuses, without the tasks) and **Delete this board**.
- A **workspace** is a named area that holds boards, with a short line on what it is for. Create one with **New
  workspace** in that menu or on the project's Overview. It only organises: tasks, schedules, agents and shared folders
  stay shared across the whole project.

Once a project has more than one workspace or board, the sidebar lists its workspaces (the plus beside a workspace adds
a board to it), and the Overview shows a card for each. A **workspace page** stacks its boards in the order you
choose. Fold a board away with the arrow in its header, **Move up** or **Move down** from its menu, and **Open** it to
get the full page with the toolbar, List, Schedule and History.

Deleting a board or a workspace never deletes its tasks: you choose the board they move to. A task whose status exists
only on the deleted board lands in the Backlog of the board it moves to. A project always keeps at least one board.

## Statuses

| Status | Meaning |
| --- | --- |
| **Backlog** | Not scheduled yet. A recurring task parked here is **paused**. |
| **Ready** | The scheduler may pick it up. With no schedule it runs as soon as a cell is free; with a schedule it runs when due. |
| **Running** | A cell is working on it right now. |
| **Review** | Finished and waiting for a human. |
| **Done** | Finished. |
| **Blocked** | Waiting on something, or cancelled while running. |
| **Failed** | The last attempt failed. |

Only the scheduler moves a task into **Running**. You start a task by making it Ready or by pressing **Run now**.

### Your own statuses

The seven statuses above are built in. They are the same on every board, in the same order, and cannot be renamed or
removed. You can add statuses of your own around them, for example *Investigating* between Backlog and Ready, or *Waiting
for client* before Done.

Open **Statuses** in the board toolbar and choose **Add or edit statuses**. There you can:

- **Add** a status by typing a name. It appears right after Backlog.
- **Rename** it, give it a **colour**, and **move** it earlier or later among the other columns.
- **Delete** it. If tasks are in it you choose where they go (any status except Ready and Running, which would start work).

A status of your own is a **parking column**, like Backlog: Themis never starts a task that sits in it. A task waits there
until you, or a [workflow](/docs/workflows), move it on, and when a task finishes it ends up in Done, Review, Failed or
Blocked as usual. Workflow Trigger and Task nodes can use your statuses too, so a workflow can start when a task lands in
*Investigating*. A status belongs to one board, and its name must differ from the other statuses of that board.

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
- **Run with**: what works on the task. The **placeholder program** prints the task and finishes (good for trying out
  scheduling). A **Codex agent** does the task for real in its own container, using the project owner's
  [Codex connection](/docs/codex).
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

### Between boards

When a project has several boards, work can move from one to another in two ways. Both are in the task's details panel,
under **On board**:

- **Send to...** moves the **same task** to another board. Its history, attempts, schedule and properties go with it.
  On a workspace page you can also drag a card from one board and drop it on a column of another. It keeps its status
  when the new board has it, and otherwise lands in that board's Backlog. A running task cannot be sent; cancel it first.
- **Follow-up...** creates a **new task** on another board that is linked to this one, which stays where it is. Use it
  when one finished piece of work feeds another, for example approved research that becomes a build task. The details
  panel of each shows what it follows and what followed it, and the card carries a small branch mark.

Both are written to the project's **History** with who did it. A workflow whose Trigger watches a status also starts when
a task arrives in that status on another board.

## Run now, cancel and delete

Open a task to find the actions:

- **Run now**: makes the task Ready and wakes the scheduler. A recurring task still keeps its normal schedule afterwards.
- **Cancel run**: stops the cell. The attempt is recorded as cancelled.
- **Delete**: removes the task and its attempts, after you confirm. Use the trash icon that appears when you point at a card on the board, or the one in the task's details panel. Files it wrote to a shared folder are not touched. The history keeps a note of every deleted task, with who deleted it, when, and what it was (description, status and schedule), so you can find it again.

## Project history

Themis keeps a history of what people do to a project: tasks created, moved to another column, sent to another board,
followed up and deleted, and boards, workspaces and statuses created, renamed and deleted. Each line says who did it and
when. You can look at it at every level:

- **The project Overview** shows the recent activity of the whole project. **Show everything** pages through all of it,
  and you can narrow it to tasks or to boards and statuses.
- A **workspace page** has a History tab for that workspace, and a **board page** one for that board. A task that was
  sent to another board shows up in the history of both.
- A **task's** details panel lists its own activity at the bottom of its History tab, including follow-ups made from it.

The history keeps its own copy of names, so a line still reads right after the task or board it mentions is gone. What
the scheduler does (starting a task, finishing it) is not repeated there: that is what each task's attempts show.

## Attempts and history

The **History** tab of a task lists every attempt with its status, start time and duration. Select one to see its
**result** and its full **log**. While a task is running the log updates live.
