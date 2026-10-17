---
title: Connect an agent (MCP)
group: Using Themis
summary: Let Claude Code or another agent look at a project through MCP, with one command and a key that only reaches that project.
---

# Connect an agent (MCP)

**MCP** is the standard way for an AI agent to use a program's tools. Themis speaks it, so an agent that lives outside
Themis, such as Claude Code on your laptop, can look at one of your projects: read its tasks, see how a run went, check
what it cost. You do not have to copy things between Themis and the agent by hand.

Today an agent can only **read**. Changing things (making tasks, starting runs) comes later, and the keys you make now
will stay read only when it does.

## Connect one

In the project's **Settings**, under **Access and tools**, find **Connect an agent**:

1. Press **Connect** and give the connection a name, such as the agent that will use it.
2. Press **Make the connection**. Themis opens it for you.
3. For **Claude Code**, press **Copy command** and paste it in a terminal. For other agents, press **Copy config** and
   add it to their MCP settings.

That is all. The command already holds the key, so there is nothing to type or look up.

The address in the command is the one your browser is using. If the agent runs on another computer, replace `localhost`
with the name or address of the machine that runs Themis, and make sure the agent can reach its port.

You can open a connection again with **Connect** whenever you need the command. Nothing is shown only once.

## What the agent can do

Every tool only reads, and only inside the project the key was made for.

| Tool | What it gives |
| --- | --- |
| `get_project` | The project's name, purpose, description and task properties. |
| `list_boards` | Its workspaces and boards, with the statuses of each. |
| `list_tasks` | Tasks, optionally one board's or one status's. |
| `get_task` | One task with its description, schedule, latest run and workflow stages. |
| `list_attempts` | The newest runs of a task and how each ended. |
| `get_attempt` | One run: its result, why it failed, what it used and the end of its log. |
| `list_agents` | The project's agents. |
| `list_workflows` | The project's workflows. |
| `get_usage` | What the runs used over the last days, per model. |

Usage is in **tokens**, as the agent engine reported them. Cached input is part of input and reasoning is part of
output, so the numbers are not meant to be added together. A run that was cancelled in the middle of a turn reports
nothing, so what it used is missing.

## Keeping it safe

> **Treat the key like a password.** Anyone who has the command can read this project: its tasks, descriptions, results
> and logs. Do not paste it in a chat or commit it to a repository.

- A key reaches **one project**. An id from another project, even one of yours, is answered as if it did not exist.
- Keys are stored encrypted, like your other secrets. If you ever change `THEMIS_SECRET_KEY`, old keys cannot be shown
  any more: remove them and make new ones.
- **Remove** a connection to cut an agent off at once. The next thing it asks is refused.
- The values of keys and connections that your agents use are not returned. Agents are listed with the ids of what they
  use, and Themis already hides key values in the logs it stores.

The list shows when each key was last used, so you can see that an agent is really connected, and notice a key that
someone else is using.

## Reaching Themis from elsewhere

Themis serves MCP on the same address as the web interface, at `/mcp`. It speaks plain HTTP unless you put it behind
something that adds HTTPS, so only connect agents over a network you trust, or over HTTPS through a reverse proxy.
