---
title: Agents
group: Using Themis
summary: Configure who does the work in a project: role, instructions, harness, model, cell and folders.
---

# Agents

An **agent** is a configured worker of one project. It says who the worker is, what it was told, how it runs and what it
can reach, so a task or a workflow step only has to say *which* agent should do it.

The project's **overview** also lists its agents under **Agents**: click one to open it straight in the editor.

Open **Agents** under a project in the sidebar. The list is on the left and the first agent is already open on the right; pick another
to edit it, or press **New agent** at the top. A project starts with none, and can have as many as it needs.

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
| **Skills** | Guides it reads when a task calls for them (see below). |
| **Tools** | Extra tools it can use, as MCP servers (see below). |
| **Keys** | Stored keys its commands can use (see below). |

When the agent runs, its prompt starts with who it is and its instructions, then the task, then a list of the folders it
has and whether each is read only. The project's `shared` folder is always among them.

## Skills

A **skill** is a folder with a `SKILL.md` file: a name and a description between two `---` lines, then instructions. The
description is how an agent decides when a skill applies, so say *when* to use it. Skills belong to a project: create
and edit them under **Skills** on the project overview, then tick the ones an agent should have on its page.

- A skill folder can hold more than `SKILL.md`: scripts or reference files you put there on disk
  (`data/projects/<project id>/skills/<name>/`) are given to the agent too, and the editor leaves them alone.
- Each run gets its own copy of only the skills the agent has, mounted **read only** at `/workspace/.agents/skills`, where
  Codex looks for them. An agent cannot change a skill, and does not see the ones it was not given.
- Deleting a skill takes it away from the agents that had it.

## Tools

A **tool** is an MCP server that gives an agent more to work with, such as a file system, a search service or a database.
Add them under **Tools** on the project overview, then tick the ones an agent should have.

- **With a command**: type the command line (`npx -y @modelcontextprotocol/server-filesystem /workspace`). It is started
  inside the agent's container, so the image must have what it runs. Under **Settings** you can add plain settings as
  environment variables, and an administrator can add keys.
- **At a web address**: the URL of a server on the web, with an optional key sent as a bearer token.

When an agent is saved, the commands of its tools are looked up in the image it runs in, and anything that is missing is
reported on the page, because an agent whose tool fails to start just carries on without it. The check needs the image on
this machine (see [Settings](/docs/settings) for the Codex image). A tool is written into the agent's Codex configuration
for each run, in memory.

## Keys

An administrator can give an agent stored keys (Settings, Keys). They are available to the agent's commands as environment
variables named after the key in capitals, shown on the page: a key called "GitHub token" is `$GITHUB_TOKEN`.

- A key reaches the cell as an in-memory file and is exported by the cell's start script. It is never on the command line,
  so it does not show in the host's process list.
- Everything the cell prints is scrubbed before it is stored: the value of a key is replaced by `[hidden]` in the log and
  the result. This stops accidents such as printing the environment. It **cannot** stop an agent that deliberately
  re-encodes a value, so only give a key to an agent you trust with it.
- Only administrators can give keys to agents and tools, because a key is paid for or trusted by the whole installation.
  Everyone can see which keys exist (names only) and which an agent has.
- If a key is deleted, agents and tools lose it; a run that finds a key, skill or tool missing stops with a note that says
  which.

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
- Removing a shared folder, skill or tool from the project also removes it from the agents that had it.
- Agents are saved with the **Save changes** button; switching to another agent without saving drops your edits.
