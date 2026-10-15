---
title: Workflows
group: Using Themis
summary: Draw a workflow, test it, and look back at every run, node by node.
---

# Workflows

A project keeps a **library of workflows**, listed in the **Workflows** section of its Settings. Click a workflow there
to edit it, or use the trash icon to delete it (with its run history). Each workflow belongs to the project it was made
in.

**Workflows** in the sidebar, and **New workflow** in the project's Settings, open an empty editor with a Start node. A new
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
| **Agent** | Hands instructions to one of the project's [agents](/docs/agents) and waits for it. The result of the node before it is passed along, and so is the task behind the run: the task that started it, or the task it is a stage of (its title and description). That is how a ticket steers a workflow, see [Steering a run from the task](#steering-a-run-from-the-task). |
| **Condition** | Checks the previous node's result or status and follows the **Yes** or **No** output. |
| **Splitter** | Sends the run down 2 to 4 **branches** that run at the same time. Each branch can have a rule: only when the result contains some text, and only some of the files. See [Branches](#branches-running-side-by-side). |
| **Merger** | Waits for its branches, then carries on once with all of them: their results in one text and their working folders side by side. See [Branches](#branches-running-side-by-side). |
| **End** | Finishes a path with an outcome (success, failed or needs review) and a note. |
| **Folder** | Not a step: hands a [shared folder](/docs/cells#shared-folders) to an Agent node (see below). |

Select a node to configure it in a window that opens beside it, over the canvas. The canvas does not move or resize, and
the window follows the node when you drag it or pan the canvas. Drag the window by its title bar to pin it where you want
it: it then stays put while you select other nodes, until you close it (the **x**, **Esc**, or a click on empty canvas).

Select a connection (click the line) to choose how it is drawn: **Organic**, a smooth curve, or **Angular**, a line that
only runs straight up, down or sideways. The choice belongs to that one connection and is saved with the workflow. It
does not change how the workflow runs.

The small box floating in the top right of the canvas holds editor options. **Snap to grid** (on by default) makes a node
you drag land on the dotted grid; switch it off to place nodes freely. It is remembered in this browser, not in the workflow.

### Saved nodes

A node you set up once can be kept for reuse. Select the node and press the **star** next to its title in the window: the
node, with its name and every setting, is kept under the built-in node of its kind in the palette. A kind that has saved
nodes shows how many, with a chevron: unfold the Agent node, for example, to see the saved agents. Click a saved node or
drag it onto the canvas to get a copy. The star stays lit while the node is exactly what was saved; press it again to
remove it from the saved nodes. A saved node also has a small **x** when you point at it.

- Saved nodes belong to the **project**, and everyone working in the project sees them. They keep the ids of that
  project's agents, folders and boards, so they would mean nothing in another project.
- Which kinds are unfolded is remembered in this browser, not in the workflow.
- A project keeps up to 100 saved nodes.
- A copy is an ordinary node: changing it does not change the saved one, and the other way round. If an agent or folder a
  saved node points at is deleted, the copy fails with a note, like any node would.

### The Agent node

Pick an **agent** and write the **instructions** for this step. The agent's own instructions, model, cell and folders apply,
and what you write here is the task it is given. With **No agent** the node runs a plain Codex agent, as before.

The window of an Agent node has two tabs. **Settings** holds the name, the agent and what it should do. **Advanced** holds
**If it fails** (stop the whole workflow, the default, or carry on to the next step) and **Cell and folders**: a step can
change the cell size or mount extra [shared folders](/docs/cells#shared-folders) (or join Folder nodes to it, see below) for
this one run, on top of what the agent has. The cell stays on **Automatic** (the agent's cell) until you press
**Customise**. A dot on the Advanced tab tells you something in there is not at its default. Nodes with nothing advanced
to set show no tabs.

If an agent is deleted, the nodes that used it fail with a note that says so until you pick another.

### Working folders in a workflow

Each Agent node starts in a **fresh working folder**. Under **Working folder** a node can instead choose **Continue in the
previous folder**: it then works in the folder of the step before it, sees the files that step left, and is told what
every earlier step changed there (see [Continuing in a working folder](/docs/cells#continuing-in-a-working-folder)).

- A **Condition** or an **End** hands the folder on, so continuing works across a branch.
- The **first** step of a run has no step before it. In a stage of a task it continues in the folder the stage before it
  ended in; started by a task moving into a status, in the folder that task last worked in; otherwise it is fresh.
- A **Task** node that creates a task has the same choice. The new task, and the workflows it plays as stages, then
  start in that folder, so a task a workflow makes can carry on the work of the workflow that made it.

### Handing folders to an agent

A **Folder** node chooses one of the project's shared folders and how the agent may use it (read and write, or read only).
Join it to an agent by dragging from the teal square on the Folder node to the teal square on the left of the Agent node. The line is
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

## Branches: running side by side

A connection point holds **one line**. Dropping a new line on a point that already has one replaces the old line. So what
happens next is never a guess: to run two things after a step, use a Splitter; to wait for two, use a Merger. (A Folder may
still feed several agents, and an agent take several folders.)

**Splitter.** One input at the top, 2 to 4 branch points along the bottom. Name the branches in its window; the names show
under the points. Every branch is sent the result of the step before it, and the branches run **at the same time**.

- **Only when the result contains**: a branch whose rule is not met is not sent anything, so a Splitter can also choose
  between ways. Nothing running after it waits for a branch that was not sent.
- **Only these files**: the branch works on just those paths of the working folder (`src`, `docs/**`, `*.md`, separated by
  commas; a folder name means everything in it).
- **Working folders.** A step in a branch that is set to **Continue in the previous folder** works on a **copy** of the
  folder of its own, so branches never write into the same files. The copy is only made when a step asks to continue; a
  branch that does not use the folder costs nothing. The copy shows in the workflow steps as "copy of the folder".

**Merger.** 2 to 4 branch points along the top, one output at the bottom. It runs once, when **every** branch has either
arrived or can no longer arrive: a Condition that went the other way, or a branch that was not sent anything, never holds
it up. It then carries on with:

- **The results**, in one text with a heading per branch (so the next agent knows which is which).
- **The folders**, side by side: every branch that worked in a folder is copied into a folder of the Merger's new working
  folder, named after the branch: the **Folder name** you gave that point, or else the name of the node that sent it
  (`research-a/`). The next agent is told what is in there. Only the private working folder is combined; shared folders
  stay shared.
- **If a branch fails**, the Merger fails and says which branch and why, and the ticket is blocked with that reason. Set
  **Merge the ones that worked** to carry on with the others (the run is still marked as failed, as a failed step is).

**Limits and good to know**

- Branches that need a cell wait for a free one like any task. The resource budget decides how many run at once; the
  rest are queued, and the time limit only starts when a cell starts, so a branch is never failed for waiting its turn.
  A Merger waiting holds no cell.
- When a branch fails, the other branches finish what they are doing and **start nothing new**.
- Stopping a run stops every branch and the cells they started.
- Workflows made before this rule can have several lines on one point. They keep running as they did, one line after the
  other, and are drawn **in amber** with a note; put a Splitter or a Merger there to say what you mean.
- A workflow that nests other workflows (a Task node that runs a task that plays a workflow) counts against the same
  limit of workflows playing at once as before; many parallel branches that each start one use it up faster.

## How a run works

- Nodes run **one at a time**, in the order the lines lead, until a [Splitter](#branches-running-side-by-side) sends the
  run down several branches: those run side by side.
- A node that fails stops its path. An agent can be told to **carry on** instead.
- A node that more than one path leads to runs once, when the first of them arrives. To wait for all of them, put a
  [Merger](#branches-running-side-by-side) in front of it.
- A **Task** node creates a real task in the project, which shows on its board like any other. An **Agent** node also makes
  a task to run its step (so the budget, the cell and the history work as for any task), but it is marked as a **workflow
  step** and kept off the boards and out of the counts. Show them with the small workflow button in a board's taskbar
  (off by default; it is remembered per project in this browser). A step starts without the usual wait before a Ready task
  starts, because its workflow is already waiting for it.

### Watching a test run

A test run is played on the canvas, so you can see where it is. While it runs, the nodes still to come are dimmed, the
ones that finished are nearly fully lit (and pulse once as they finish), and the one playing has a thicker border with a
shine travelling around it. The lines the run has gone along are drawn thicker, and when the run moves to the next node
a glow travels along the line first. When the run ends, everything fades back to normal. **Run details** opens the full
log of the run on the Runs tab.

## Workflows and tasks play each other

- A **Task node** can create, update or run any task of the project, and wait for it.
- A **task** can play workflows: set the task's **Run with** to **Workflow** and pick one from the library. Use **Add a
  stage** to pick more, and the arrows to put them in order. When the task runs, the workflows run one after the other
  instead of a container.

So workflows orchestrate tasks, and tasks orchestrate workflows. A task that plays workflows does not take up one of the
resource budget (Settings, Resources), because it mostly waits for the tasks inside it. A workflow that would end up playing
itself through its own tasks is stopped, and so are chains nested more than five levels deep.

### Steering a run from the task

A workflow says **how** to work. What a particular run should **focus on** belongs on the task: its **description** is
given to every Agent node of the workflows it plays, right after that node's own instructions and before the result of
the step before it, as "This is a stage of the task ...". So the same workflow can be pointed somewhere else by editing the
ticket, and the workflow's instructions can stay general ("improve the game toward the task's focus").

- A task with no description still tells its agents its title.
- A step that only does housekeeping (syncing a clone, publishing a change) should not take the task's focus as its own
  job. Turn off its **Include task title and description** switch and it is given nothing from the task. The switch
  is on by default, so a step that thinks about the work needs nothing set.
- A test run from the editor has no task, so nothing is added.
- Under each stage in the task's panel, **Step instructions** shows what its agents are told (the workflow's instructions
  as they are now, and who does each). **Edit step** opens the workflow editor with that node selected and its window open.
  Changing instructions there changes the workflow for every task that plays it.

### Stages on a task

Each workflow a task plays is a **stage**. They are listed at the top of the task's panel, in the order they play, and
under a divider on the task's card on the board, where you can follow a run without opening anything:

| Icon | Stage |
| --- | --- |
| Dashed circle | Not started yet. It is listed as soon as you pick it. |
| Spinner | Running |
| Check | Done, with how long it took |
| Cross | Failed |
| Slashed circle | Cancelled |

A stage that has started unfolds (the one that is running opens by itself) into a small track: the node it has just
come from, the node it is working on now, and the node that comes next. When the workflow branches, for example at a
**Condition**, every way on is listed one under the other with the answer that leads there (Yes or No). Once the node has
answered, the ways not taken are dimmed. A node that failed stops the track, and what came after it is dimmed. **Run
details** opens the full run.

- On a card, finished stages fold into a count ("2 done") and only the next few that are still open are listed, with
  "+N more" for the rest. The track of the running stage shows the node before as a dot (point at it for the name), and
  it wraps or shortens its names when the card is narrow.
- A stage that fails ends the attempt, and the stages after it stay not started.
- The panel lists what each stage's steps reported, under its track: a short summary that opens in full when you click it
  (a pull request link in it is a link). The same text, one section per stage, is the task's **result** in its History.
- Stages connect through the working folder: a stage starts in the folder the one before it ended in, and any Agent node
  in it set to **Continue in the previous folder** picks up those files. Nodes left on a fresh folder are unaffected, so
  a stage only shares files with the stage before it when you ask it to.
- Starting the task again starts every stage over. The panel always shows the latest attempt; earlier runs stay under
  **History**.
- Deleting a workflow takes it out of the tasks that played it.

## Run history

The **Runs** tab keeps every run. Pick one to see its nodes in the order they ran, with a check or a cross for each.
Click a node to unfold it:

- the **error** (why it failed) or the reason it **did not run**,
- the node's **result**,
- its **log**, for task and agent nodes the full log of what the agent said and ran. Use the enlarge button to read it
  in a big window.

Nodes that failed unfold on their own. Nodes the run never reached are listed under **Did not run**, each with the
reason: a failed node before it, the other side of a condition, or no line leading to it.

Node results open as formatted Markdown, with clickable web links and **Copy** buttons on code blocks. Switch to
**Raw** for the original text, or **Rendered** for the report. Long results scroll inside the viewer. Selecting
another run opens its results in Rendered view.

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

- **Most automatic moves in a row**: the limit above. Set it on a project in its Settings, **Cells and automation**, on a task in its
  **Automation guard** box.
- **Wait before starting**: how long after a change a task, or a workflow for it, may start. This is the same delay as
  **Settings, Wait before a Ready task starts**.

You can see this from the board:

- A status column with a **⚡ number** in its header is watched. Click it to see which workflows start when a task is
  moved there, and to open one.
- A card shows the workflow run it started, with the step it is on, until the run is over.
- The **History** tab of a task lists the runs it started, newest first, with a link to each.
