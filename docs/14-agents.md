---
title: Agents
group: Using ThemisForge
summary: Configure who does the work in a project: role, instructions, harness, model, cell and folders.
---

# Agents

An **agent** is a configured worker of one project. It says who the worker is, what it was told, how it runs and what it
can reach, so a task or a workflow step only has to say *which* agent should do it.

Open **Agents** under a project in the sidebar. The list is on the left; pick an agent to edit it, or press
**New agent**. A project starts with none, and can have as many as it needs.

## What an agent has

| Part | What it is for |
| --- | --- |
| **Name** | Unique within the project. This is what you pick in a task or a workflow. |
| **Role** | One line on what it is responsible for, shown in lists so it is clear what each agent is for. |
| **Description** | For people: a longer note on what the agent does. The agent never sees it. |
| **Harness** | The program that runs inside the cell. Codex today (see [Connecting Codex](/docs/codex)). |
| **Model** and **reasoning effort** | Empty means the ones in **Settings, Codex agents**. |
| **Instructions** | For the agent: always put in front of whatever task it is given. How to work, what to produce, what to avoid. |
| **Cell** | The size of its container. **Automatic** by default (the project's cell, which uses the defaults in Settings); press **Customise** only if this agent needs something different. |
| **Folders** | The [shared folders](/docs/cells#shared-folders) mounted in its workspace, and whether it may write to them. |

When the agent runs, its prompt starts with who it is and its instructions, then the task, then a list of the folders it
has and whether each is read only. The project's `shared` folder is always among them.

## Using an agent

- **On a task**: choose it under **Run with**. The task then runs with the agent's instructions, model, cell and folders.
- **In a workflow**: pick it in an Agent node. The node's instructions are the task it is given for that step, and the
  node can change the cell or add folders for that step only. See [Workflows](/docs/workflows).

Both use the project owner's Codex connection, and both take part in the [resource budget](/docs/settings#resources) like
any other cell.

## Cells, from default to step

The size of a cell is decided in layers, each one only changing what it fills in:

1. **Settings, Cells**: the defaults for everyone.
2. **The project**: its **Cell** section, when you create or edit the project.
3. **The agent**: its **Cell** section.
4. **A workflow step**: the Agent node's **Cell and folders**.

Everywhere a cell is chosen (a project, an agent, a workflow step) it starts on **Automatic**, with a line saying what that
means, for example "Uses the project's cell: 1 CPU, 1024 MB, 1 h". **Customise** shows the fields, and **Back to automatic**
takes the overrides away again. Fields left empty while customising still use the layer above.

An image is only worth setting if it has what the agent needs (such as the Codex CLI). By default a Codex agent uses the
Codex image from Settings.

## Good to know

- Names are unique per project, so two agents in different projects can share a name.
- Deleting an agent does not delete the tasks it did. A task keeps running as a plain Codex task; workflow nodes that
  used the agent fail with a note until you pick another one. An agent that is running a task cannot be deleted.
- Removing a shared folder from the project also removes it from the agents that mounted it.
- Agents are saved with the **Save changes** button; switching to another agent without saving drops your edits.
