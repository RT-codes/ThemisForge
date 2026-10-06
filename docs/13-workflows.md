---
title: Workflows
group: Using ThemisForge
summary: Draw a workflow, test it, and look back at every run, node by node.
---

# Workflows

Every project has a **Workflow editor**. Draw nodes, connect them, and press **Test run** to run the whole thing. The
workflow is saved automatically as you edit.

## Nodes

| Node | What it does |
| --- | --- |
| **Start** | A run begins here. A workflow can have several Start nodes; a run begins at all of them. |
| **Trigger** | Also begins a run. Schedules and events are not automatic yet, so for now it behaves like Start. |
| **Task** | Creates a task, updates one, or runs one by its title. A task that becomes **Ready** runs like any other task and the node waits for it. |
| **Agent** | Hands instructions to a Codex agent (see [Connecting Codex](/docs/codex)) and waits for it. The result of the node before it is passed along. |
| **Condition** | Checks the previous node's result or status and follows the **Yes** or **No** output. |
| **End** | Finishes a path with an outcome (success, failed or needs review) and a note. |

Select a node to configure it in the panel on the right.

## How a run works

- Nodes run **one at a time**, in the order the lines lead.
- A node that fails stops its path. An agent can be told to **carry on** instead.
- A node that more than one path leads to runs once.
- Task and Agent nodes create real tasks in the project, so they also show up on the Tasks page.

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
