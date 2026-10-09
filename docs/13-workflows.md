---
title: Workflows
group: Using Themis
summary: Draw a workflow, test it, and look back at every run, node by node.
---

# Workflows

A project keeps a **library of workflows**, listed in the **Workflows** section of its overview. Click a workflow there
to edit it, or use the trash icon to delete it (with its run history). Each workflow belongs to the project it was made
in.

**Workflows** in the sidebar, and **New workflow** on the overview, open an empty editor with a Start node. A new
workflow is **only saved once you change something in it**, so opening one and walking away leaves nothing behind. It
gets the first free name, "Workflow 1", "Workflow 2" and so on, which you can change at the top.

In the editor, draw nodes, connect them, and press **Test run** to run the whole thing. Changes are saved
automatically. The buttons left of the title:

- **Save** saves right now (and keeps a new workflow even if you have not changed anything yet).
- **Load** opens a list of all the project's workflows. Pick one to open it, or start a new one.
- **Recent** drops down the last five workflows you edited, for a quick switch.

Whatever you were editing is saved before the next workflow opens.

### Selecting several nodes

Hold **Shift** and drag on the canvas to draw a box around nodes, or hold **Shift** or **Ctrl** and click nodes to add
them to the selection one by one (click a selected node again to take it out). A dashed box with some room around it shows
what is selected, and its toolbar offers **Deselect** and **Delete** for all of them at once. Drag any selected node to
move them all together. **Esc** lets go of the selection.

## Nodes

| Node | What it does |
| --- | --- |
| **Start** | A run begins here. A workflow can have several Start nodes; a run begins at all of them. |
| **Trigger** | Begins a run by itself. Set to **A task moves into a status**, it starts the workflow whenever a task of the project is moved into (or created in) that status, from the board, the API or another workflow. The status can be one of the seven built-in ones or a [status you added](/docs/tasks#your-own-statuses) to a board. With **Where** it can watch only one workspace or one board (a status of your own belongs to one board and only fires there). The steps after it can use that task. Schedules are not automatic yet; a Trigger set to anything else behaves like Start. |
| **Task** | Creates a task, updates or runs one by its title, or moves **the task that started this run** (needs a Trigger of the kind above). It can work on a chosen **board**: create the task there, or send the moved task there. A created task can be a **follow-up** of the task that started the run. A task that becomes **Ready** runs like any other task and the node waits for it. |
| **Agent** | Hands instructions to one of the project's [agents](/docs/agents) and waits for it. The result of the node before it is passed along, and so is the task that started the run (its title and description). |
| **Condition** | Checks the previous node's result or status and follows the **Yes** or **No** output. |
| **End** | Finishes a path with an outcome (success, failed or needs review) and a note. |
| **Folder** | Not a step: hands a [shared folder](/docs/cells#shared-folders) to an Agent node (see below). |

Select a node to configure it in the panel on the right.

### The Agent node

Pick an **agent** and write the **instructions** for this step. The agent's own instructions, model, cell and folders apply,
and what you write here is the task it is given. With **No agent** the node runs a plain Codex agent, as before.

Under **Cell and folders** a step can change the cell size or mount extra [shared folders](/docs/cells#shared-folders) (or join Folder nodes to it, see below) for
this one run, on top of what the agent has. The cell stays on **Automatic** (the agent's cell) until you press **Customise**. If an agent is deleted, the nodes that
used it fail with a note that says so until you pick another.

### Handing folders to an agent

A **Folder** node chooses one of the project's shared folders and how the agent may use it (read and write, or read only).
Join it to an agent by dragging from the teal square on the Folder node to the teal square under the Agent node. The line is
dashed and teal and has no arrow, because it is not a step: it only says "this agent gets this folder".

- The agent gets the folder for that step, **on top of** its own folders and the project's `shared` folder. Several Folder
  nodes can feed one agent, and one Folder node can feed several agents.
- Only a Folder can be joined to an agent's folder point, and nothing else can be joined to a Folder. The editor refuses
  other lines while you drag.
- If the same folder is also named in the agent node's own **Extra folders** list, that list decides its access.
- Folder nodes are not steps, so they never run and never appear in a run's history, not even under "Did not run". A Folder
  node that is not joined to anything does nothing.
- A Folder node with no folder chosen stops the agent it is joined to, with a note that says which node. If the folder
  was removed from the project, the agent's run fails with a note too.
- The agent's panel lists the folders handed over on the canvas, read only. Change them on the Folder nodes.

## How a run works

- Nodes run **one at a time**, in the order the lines lead.
- A node that fails stops its path. An agent can be told to **carry on** instead.
- A node that more than one path leads to runs once.
- Task and Agent nodes create real tasks in the project, so they also show up on the project's first board.

### Watching a test run

A test run is played on the canvas, so you can see where it is. While it runs, the nodes still to come are dimmed, the
ones that finished are nearly fully lit (and pulse once as they finish), and the one playing has a thicker border with a
shine travelling around it. The lines the run has gone along are drawn thicker, and when the run moves to the next node
a glow travels along the line first. When the run ends, everything fades back to normal. **Run details** opens the full
log of the run on the Runs tab.

## Workflows and tasks play each other

- A **Task node** can create, update or run any task of the project, and wait for it.
- A **task** can play a workflow: set the task's **Run with** to **Workflow** and pick one from the library. When the task
  runs, the workflow runs instead of a container, and the attempt history shows its progress with a link to the full run.

So workflows orchestrate tasks, and tasks orchestrate workflows. A task that plays a workflow does not take up one of the
resource budget (Settings, Resources), because it mostly waits for the tasks inside it. A workflow that would end up playing
itself through its own tasks is stopped, and so are chains nested more than five levels deep.

## Run history

The **Runs** tab keeps every run. Pick one to see its nodes in the order they ran, with a check or a cross for each.
Click a node to unfold it:

- the **error** (why it failed) or the reason it **did not run**,
- the node's **result**,
- its **log**, for task and agent nodes the full log of what the agent said and ran. Use the enlarge button to read it
  in a big window.

Nodes that failed unfold on their own. Nodes the run never reached are listed under **Did not run**, each with the
reason: a failed node before it, the other side of a condition, or no line leading to it.

A run that is still going can be cancelled; this also stops the container its current task is running in.

## Starting workflows from the board

A Trigger set to **A task moves into a status** only looks at where a task lands, not where it came from. Together with
the Task node's **Move the task that started this run**, this lets a workflow act as a step on the board: for example
an agent that picks up everything moved into **Backlog**, splits it, and moves the original to **Ready**.

- A task moved by a workflow node starts other workflows too, so workflows can hand work to each other.
- The task an **Agent** node creates for itself never starts a workflow.
- A workflow is not started again for the same task while its previous run for that task is still going, nor within the
  start delay (**Settings, Wait before a Ready task starts**, which a project or a task can override). That slows down a workflow that moves a task back into
  the status that starts it; it does not forbid it.
- Moves made while Themis is stopped do not start anything.

## Workflows between boards

Boards can be connected by workflows. A typical pair: a Trigger on the Research board's **Review** status whose Task
node *creates a follow-up* on the Development board, and a Trigger on the QA board's **Failed** status whose Task node
*sends the task back* to Development. Everything a workflow does shows in the project's
[history](/docs/tasks#project-history) as "Workflow <name>", so you can see which one moved what.

- **Send to board** on **Move the task that started this run** moves the same task to another board, with its history.
- **Follow up** on **Create a task** links the new task to the one that started the run, like the **Follow-up** button
  in the task panel. The new task takes the property values of the first.
- A step makes its task **once per run**. Running the same step again finds the task it already made.

### The automation guard

Two boards that send a task back and forth would never stop, so Themis counts. Every time a workflow moves or makes a
task, that task's count goes up by one; when a person moves it, edits its status or sends it, the count starts from
nothing. When the count would pass the limit (10 by default) the step stops with a reason, the run fails, and the
project's history says why. Two things can be tuned, each in three layers (**Settings**, then the **project**, then a
single **task**; an empty box follows the layer above):

- **Most automatic moves in a row**: the limit above. Set it on a project in **Edit project**, on a task in its
  **Automation guard** box.
- **Wait before starting**: how long after a change a task, or a workflow for it, may start. This is the same delay as
  **Settings, Wait before a Ready task starts**.

You can see this from the board:

- A status column with a **⚡ number** in its header is watched. Click it to see which workflows start when a task is
  moved there, and to open one.
- A card shows the workflow run it started, with the step it is on, until the run is over.
- The **History** tab of a task lists the runs it started, newest first, with a link to each.
