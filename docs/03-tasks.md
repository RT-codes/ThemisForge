---
title: Projects and tasks
group: Using Themis
summary: The project dashboard, task statuses, custom properties and the board.
---

# Projects and tasks

## The project pages

Selecting a project in the sidebar opens its **Overview** and expands its sub pages. The overview is the project's
dashboard: how many tasks are ready and running, how many are scheduled for today and the next 7 days, what needs
attention, the next runs, a card for each workspace, and the recent activity. A workspace card lists its boards as
tags (a tag opens that workspace with that board unfolded and the others folded) and its latest tasks with their
status; a task opens on its own board with its panel showing. When something is not set up (an agent
whose file has a problem, a connection an agent wants that the project lacks, a tool that needs a sign in) a **Needs
setup** strip at the top says so and links to the section that fixes it. Everything you configure is on the project's
**Settings** page (see below). Under a project the sidebar lists its pages (**Overview**, **Settings**, **Files**,
**Agents** and the **Workflow editor**) and then **Workspaces**, with the workspaces themselves indented below it, where your work lives. The small plus buttons beside a page or a workspace
(a new agent, workflow or board) appear when you point at its row; the one beside **Workspaces** adds a workspace.

### Project settings

**Settings** under a project is where it is set up, in sections you can fold away:

- **General**: its icon, name, what it is for and its description.
- **Cells and automation**: the container its tasks run in, and its automation guard (see [Scheduling](/docs/scheduling)).
- **Task properties**: its custom properties (see below).
- **Agents**, **Workflows**, **Connections**, **Tools**, **Skills** and **Shared folders**: each with its list and its
  buttons, as described on the pages for [agents](/docs/agents), [workflows](/docs/workflows),
  [connections](/docs/connections) and [cells](/docs/cells).
- **Danger zone**: delete the project.

The overview's **Needs attention** section brings together tasks waiting for review and failed tasks across all boards.
It also shows recurring tasks back in Ready whose last run failed; their next occurrence still happens. Review tasks
come first, then failures, with the most recently changed tasks first in each group. Use **View result** on a row to
open that task's **History** panel on its board, with the latest attempt's result and log. This works even when board
filters hide the task's card. If the task has moved or been deleted, the board says so. The section shows five tasks
at first, with a total count and **Show everything** for the rest, and
refreshes while the page is visible. The list follows current statuses and latest attempts: a review moved to Done
disappears, as does a recurring failure when another attempt starts or its latest attempt no longer failed.
If the list cannot refresh, it shows an error and retries
automatically instead of reporting that nothing needs attention.

## Workspaces and boards

Every project starts with one workspace, **Main**, that holds one board, **Tasks**. Open it from the sidebar to see
your tasks. When one board is not enough, for example because research, building and publishing have different steps,
you can split the work up:

- A **workspace** is a named area with a short line on what it is for. It holds one or more boards, shown stacked on
  its page in the order you choose. It only organises: tasks, schedules, agents and shared folders stay shared across
  the whole project. Create one with **New workspace** on the Overview or in a board's **...** menu, and rename or
  delete it from its own **...** menu.
- A **board** is one Kanban with its own [statuses](#your-own-statuses). Every task lives on exactly one board. Add one
  with **New board** on a workspace page (or the plus beside the workspace in the sidebar). A board's **...** menu has
  **Edit board**, **Duplicate** (the same statuses, without the tasks) and **Delete board**.

Point at a project or a workspace in the sidebar and a **pencil** appears beside it (before the plus). It opens a small
popup right there where you can change its **icon** (click it, then search the Lucide icon set by name), its **name**,
a one-line note on **what it is for**, and its **description**. The same fields are under **General** in the project's
Settings and in the **Edit workspace** dialog.

On a workspace page, fold a board away with the arrow in its header, use **Move up** or **Move down** from its menu,
and **Open** it to get its own page with a header and four views of the **same** tasks:

- **Board**: columns by status, with drag and drop. Search, order and filters apply across the board.
- **List**: a table, handy when there are many tasks. The same search, order and filters apply here too.
- **Schedule**: a timeline and **Up next** list of this board's tasks that will run in the next 24 hours or 7 days.
  The project overview shows upcoming runs across all boards.
- **History**: what was done on this board: tasks created, moved, sent or deleted, and changes to its statuses.

Board and List show each selected board filter beside the controls, such as **Schedule: Repeating** or **Priority: High**.
Press a filter's **x** button to remove just that value, keeping your search, order and other filters. These choices are
remembered in this browser. Filters for an individual status stay in that column's menu.

The header shows how many tasks are running, ready, waiting for review or failed, when the next run is due, and
whether the scheduler is on and how many cells are busy. A workspace page also has a **History** tab for the whole
workspace.

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

Every status has an **icon** in front of its name (Backlog is a stack of boxes, Ready a package, Running an open package,
Review a package with a magnifier, Done a ticked package, Blocked and Failed a package with a minus or a cross) and an
**(i)** beside its title: point at it to read what the status is for. A new status of your own starts with a plain box.
The **pencil** in a column's header edits it. For a status of your own you can change its **icon**, **name**, **colour**
and the text of its **(i)**, which is what you write it is for. For a built-in status the pencil only shows it, locked,
because the seven are the same on every board.

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

## Why a task failed

A failed task's card says why in a sentence, and the task's details show the whole explanation above the tabs: what
happened, **what to do** about it when that is known, and the last lines of the log (the **History** tab has the same for
every failed attempt). Who found the reason is shown too:

- **Found by Themis**, from what the run did: the program's exit code, the error the agent's program printed, a cell that
  could not start, or a step of a workflow that failed (the card then names the step).
- **Written by the agent**. An agent that cannot do the task because something is missing (a tool in the cell, a key, a
  folder, access, an instruction that is unclear) is told to stop and say so instead of inventing a way around it. The
  attempt then fails with its words, even when the program itself ended normally. The work it did stays in its working
  folder.

When the model provider is only briefly unable to serve a run (for example "Selected model is at capacity"), Themis starts
that run again by itself, three times by default, waiting 30 seconds, then 90, then 180 (changeable under **Settings, Cell
package**). This happens inside the same attempt, the log says so, and the run is told that it continues the work already
in its folder. If the provider is still failing
after that, the attempt fails and says so. Errors that need you, such as a usage limit or a model that does not exist, are
not retried.

## Task options

**Click a card** to select it. A selected card unfolds to show more of the task: its whole description, how it runs, when
it last ran and how that ended, and every stage. All the other cards stay compact. Click it again, press **Esc** or click
on empty space to fold it. To open the task's **details panel**, use the **pencil** that appears when you point at a card
(it is always shown on a selected card and on touch screens), next to the trash. Several cards picked with Ctrl or Shift
(see [Several tasks at once](#several-tasks-at-once)) do not unfold.

The top of the details panel has **Run now** (or **Cancel run**) on the left, with when the task last ran
beside it, and **Cancel** and **Save changes** on the right. Under it is a card with the task's **title**, which you
edit right there (it is saved with **Save changes**, like the rest), and the **trash** icon. Then comes a **taskbar**: the board the task is on, its **status**, and a switch
between **Details** and **History**. The status is changed right there and takes effect at once, like moving the card
(a running task has to be cancelled first). Everything else is saved with **Save changes**, and sits on two tabs of
**Details**:

**General**

- **Description**: what needs doing, in more words. It is passed to the cell. For a task that plays workflows it is the
  brief of the run: every agent step of its stages is given it, so it is where you say what this run should focus on
  (see [Steering a run from the task](/docs/workflows#steering-a-run-from-the-task)).
- **Run with**: what works on the task. The **placeholder program** prints the task and finishes (good for trying out
  scheduling). A **Codex agent** does the task for real in its own container, using the project owner's
  [Codex connection](/docs/codex). One or more **workflows** play in order, each as a stage you can follow in the
  task's panel (see [Stages on a task](/docs/workflows#stages-on-a-task)).
- **Custom properties**: your own fields, see below.

**Schedule & automation**

- **Ask for review when it succeeds**: one-off tasks end in **Review** instead of **Done**, so a human looks at the
  result first.
- **Schedule**: manual, once, or recurring. See [Scheduling](/docs/scheduling).
- **Automation guard**: how much workflows may move this task around. See
  [the automation guard](/docs/workflows#the-automation-guard).

## Custom properties

Each project defines its own fields, shared by all of its boards. Open **Task properties** in the project's **Settings**,
or choose **Custom properties** in the three-dot menu of a board page, in the workspace page's menu, or in the menu of any
board on a workspace page.

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

### Several tasks at once

Hold **Ctrl** (**Cmd** on a Mac) and click cards to pick several of them, or hold **Shift** and click to pick a run of
them. A picked card gets a ring and a check mark, and a bar appears above the board with what you can do with them.

- **Shift and click** picks every card between the one you last clicked (or the task that is open) and this one, in the
  order the column is shown. A run stays **inside one status**: shift and click on a card of another status picks only
  that card, and starts a new run from there. Shift alone replaces the selection with the run; **Ctrl and Shift** adds
  the run to it.
- The card that was selected on its own (or open in the details panel) joins the selection when you pick another one, and
  the details panel closes, so the two are not side by side.

What the bar does:

- **Move to** sends all of them to a status of this board. They land at the end of its column, in the order they had on
  the board. **Running** is not offered: only the scheduler starts tasks.
- **Delete** asks once for all of them. The project's History keeps a note of each task that was deleted.
- **Clear**, or **Esc**, lets go of the selection.

A running task cannot be moved or deleted, so it cannot be picked; one that starts running while picked drops out of the
selection. Each board keeps its own selection, so on a workspace page cards of two boards are not mixed.

### Clicking away

Click on empty space (not on a card, a button or the panel) to let go. That clears a selection, folds the card selected on
its own, and closes the task open in the details panel. If the panel holds changes that are not saved, nothing closes:
Themis asks whether to **Save** them, **Discard** them or **Keep editing**. The same question comes up when you open
another task, or start a new one, while the panel has unsaved changes. A new task that you are still writing is not
closed by clicking away.

### Between boards

When a project has several boards, work can move from one to another in two ways. Both are in the menu on the board name
in the task's taskbar:

- **Send to another board...** moves the **same task** to another board. Its history, attempts, schedule and properties go with it.
  On a workspace page you can also drag a card from one board and drop it on a column of another. It keeps its status
  when the new board has it, and otherwise lands in that board's Backlog. A running task cannot be sent; cancel it first.
- **Create a follow-up...** creates a **new task** on another board that is linked to this one, which stays where it is. Use it
  when one finished piece of work feeds another, for example approved research that becomes a build task. The details
  panel of each shows what it follows and what followed it, and the card carries a small branch mark.

Both are written to the project's **History** with who did it. A workflow whose Trigger watches a status also starts when
a task arrives in that status on another board.

## Run now, cancel and delete

Open a task to find the actions:

- **Run now**: makes the task Ready and wakes the scheduler. A recurring task still keeps its normal schedule afterwards.
- **Stop task**: stops the agent (and, for a task that plays workflows, its run and the cell under it). The attempt is
  recorded as cancelled. A running card has the same button, a small square next to its spinner, so you do not have to
  open the task. See [Stopping work](#stopping-work) for where the task goes afterwards.
- **Duplicate**: the copy icon next to the trash icon in the task's title card makes a copy of the task and opens it. The copy
  is called "Copy of ..." and always lands in the **Backlog** of the same board, so it never starts by itself. It has the
  same description, properties, schedule, agent or stages (workflows), review setting and automation guard. It does not
  have the original's attempts or history, the task it follows, or the working folder the original carried on in: a copy
  starts fresh. A recurring task's copy keeps its schedule and takes it up when you move it to Ready. A workflow step
  cannot be duplicated.
- **Delete**: removes the task and its attempts, after you confirm. Use the trash icon that appears when you point at a card on the board, or the one in the task's title card. Files it wrote to a shared folder are not touched. The history keeps a note of every deleted task, with who deleted it, when, and what it was (description, status and schedule), so you can find it again.

## Stopping work

There are two levels, and they are different on purpose.

**Stopping one task** (the square on a running card, or **Stop task** in its panel) stops that agent and nothing else.
Where the task goes depends on what it is:

| The task | After you stop it |
| --- | --- |
| One-off | **Blocked**: stopped by you, and it will not start again until you run it |
| Recurring | Back to **Ready** on its schedule: only this run is skipped, the schedule is untouched |

**Halting** is the emergency brake for a **board** (the octagon in its taskbar) or the whole **project** (next to the
project menu on its pages). Until you press **Resume** nothing in it starts: not a Ready task, not a schedule, not a
workflow trigger, not **Run now**, not a manual workflow run. A banner on the pages says so for as long as it lasts, and
it survives a restart.

- **Also stop what is running now** (on by default) stops everything running in it, workflows included. Switch it off to
  let the current work finish and only hold back what is next.
- What a halt interrupted goes to **Blocked**, like any stopped one-off task, so resuming never restarts it by itself:
  the reason for a halt is often a task that misbehaves. Its working folder is kept, so you can see how far it got.
- Tasks that were only waiting stay Ready, and go on when you resume. Recurring tasks do not catch up on what they missed
  while halted: they carry on from their next time.
- Halting a board holds that board's tasks only. Halting the project holds everything in it, including the steps of
  workflows (these steps are tasks Agent nodes make, see [workflows](/docs/workflows)). A workflow started by a task of a
  halted board is stopped with it.
- Halting and resuming are written to the project's history, with who did it.

## Project history

Themis keeps a history of what people do to a project: tasks created (or duplicated), moved to another column, sent to another board,
followed up and deleted, and boards, workspaces and statuses created, renamed and deleted. Each line says who did it and
when. You can look at it at every level:

- **The project Overview** shows the recent activity of the whole project. **Show all activity** pages through all of it,
  and you can narrow it to tasks or to boards and statuses. A line opens the board it happened on.
- A **workspace page** has a History tab for that workspace, and a **board page** one for that board. A task that was
  sent to another board shows up in the history of both.
- A **task's** details panel lists its own activity at the bottom of its History tab, including follow-ups made from it.

The history keeps its own copy of names, so a line still reads right after the task or board it mentions is gone. What
the scheduler does (starting a task, finishing it) is not repeated there: that is what each task's attempts show.

## Attempts and history

The **History** tab of a task lists every attempt with its status, start time and duration. Select one to see its
**result** and its full **log**. While a task is running the log updates live. For a task that plays workflows the result
is what its stages reported (one section per stage when there are several), so a pull request link is there without
opening the run.

Results open as formatted Markdown, with headings, lists, tables, code blocks and clickable web links. Use **Raw**
to read the original text, or **Rendered** to return to the report. Code blocks have a **Copy** button. Long results
scroll inside the viewer. Selecting another attempt opens its result in Rendered view.
