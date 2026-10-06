---
title: Workflows
group: Using ThemisForge
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

## Nodes

| Node | What it does |
| --- | --- |
| **Start** | A run begins here. A workflow can have several Start nodes; a run begins at all of them. |
| **Trigger** | Also begins a run. Schedules and events are not automatic yet, so for now it behaves like Start. |
| **Task** | Creates a task, updates one, or runs one by its title. A task that becomes **Ready** runs like any other task and the node waits for it. |
| **Agent** | Hands instructions to one of the project's [agents](/docs/agents) and waits for it. The result of the node before it is passed along. |
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
- Task and Agent nodes create real tasks in the project, so they also show up on the Tasks page.

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
