---
title: Connect an agent (MCP)
group: Using Themis
summary: Let Claude Code or another agent look at your projects through MCP, with one command and a key you can take away again.
---

# Connect an agent (MCP)

**MCP** is the standard way for an AI agent to use a program's tools. Themis speaks it, so an agent that lives outside
Themis, such as Claude Code on your laptop, can look at your work: what is going on in a project, its tasks and boards,
how a run went, how its agents are set up, what it cost, even the files in its folders. You do not have to copy things
between Themis and the agent by hand.

Today an agent can only **read**. Changing things (making tasks, starting runs, editing settings) comes later, and the
keys you make now will stay read only when it does.

## Two kinds of connection

| | Reaches | Made in |
| --- | --- | --- |
| **For one project** | That project and nothing else. | The project's **Settings**, under **Access and tools**. |
| **For all your projects** | Every project you own, and the global settings if you are an administrator. | **Settings**, under **Connections**. |

Use the first for an agent that has one job in one project, and the second for an agent that helps you run Themis
itself. Either way the agent can see exactly what you can, and not more.

## Connect one

1. Press **Connect** and give the connection a name, such as the agent that will use it.
2. Press **Make the connection**. Themis opens it for you.
3. For **Claude Code**, press **Copy command** and paste it in a terminal. For other agents, press **Copy config** and
   add it to their MCP settings.

That is all. The command already holds the key, so there is nothing to type or look up. You can open a connection
again with **Connect** whenever you need the command. Nothing is shown only once.

The address in the command is the one your browser is using. If the agent runs on another computer, replace `localhost`
with the name or address of the machine that runs Themis, and make sure the agent can reach its port.

## What the agent can look at

Everything reads. On a connection for all your projects, a tool that is about a project needs its `project_id`
(`list_projects` has them); on a connection for one project it can be left out.

**Start with the overview.**

| Tool | What it gives |
| --- | --- |
| `list_projects` | Your projects, with the number of tasks per status and when the next one starts. |
| `get_project_overview` | A project at a glance: tasks per status, the boards, what is running now, what needs a person (failed, blocked, in review, waiting for approval), what is coming in the next day, the latest events and what the last week used. |
| `get_history` | What was done in the project, newest first. |
| `list_upcoming_runs` | What is going to run in the next hours. |

**Then go down into the work.**

| Tool | What it gives |
| --- | --- |
| `list_boards` | Workspaces with their boards, columns and task counts. |
| `get_board` | One board with all of its tasks, as the board page shows it. |
| `list_tasks`, `get_task` | Tasks, optionally of one board or status, and one task in full. |
| `list_attempts`, `get_attempt` | The runs of a task, and one run with its result, why it failed, what it used and the end of its log. |
| `get_usage` | What the runs used over the last days, per model. |

**And how the project is set up.**

| Tool | What it gives |
| --- | --- |
| `list_agents`, `get_agent` | Agents with their instructions, model, cell size and what each is given. |
| `list_workflows`, `get_workflow`, `list_workflow_runs`, `get_workflow_run` | Workflows with their graph, their runs and the log of every step. |
| `list_approvals` | Steps that wait for a person to approve. |
| `list_skills`, `get_skill` | Skills and their text. |
| `list_tool_servers` | The tool servers agents can be given. |
| `list_webhooks`, `list_webhook_deliveries` | Where messages from outside land, and what arrived. |
| `list_notifications`, `list_project_connections` | Where the project sends messages, and the services it uses. |
| `list_folders`, `list_files`, `read_file` | The project's folders (the config folder too), what is in them, and the text of a file. |

**Global**, only on a connection for all your projects.

| Tool | What it gives |
| --- | --- |
| `get_settings` | The global settings. Only for an administrator. |
| `get_system_status` | How Themis is doing: the scheduler, whether cells can run, the version. |
| `list_harnesses` | The agent engines and their models. |
| `list_keys` | The names of stored keys, never their values. |

Usage is in **tokens**, as the agent engine reported them. Cached input is part of input and reasoning is part of
output, so the numbers are not meant to be added together. A run that was cancelled in the middle of a turn reports
nothing, so what it used is missing. Long lists and logs are cut to a limit, and `read_file` stops at a number of
characters, so one call cannot flood the agent.

## Keeping it safe

> **Treat the key like a password.** Anyone who has the command can read what it reaches: tasks, descriptions, results,
> logs and files. A key for all your projects reaches a lot. Do not paste it in a chat or commit it to a repository.

- A key for one project reaches **that project only**. An id from another project, even one of yours, is answered as if
  it did not exist. A key for all your projects reaches your projects and never anyone else's.
- The global settings need a key for all your projects **and** an administrator behind it.
- The values of keys and connections that your agents use are not returned. Agents are listed with the ids of what they
  use, webhooks with the end of their secret, and Themis already hides key values in the logs it stores.
- Keys are stored encrypted, like your other secrets. If you ever change `THEMIS_SECRET_KEY`, old keys cannot be shown
  any more: remove them and make new ones.
- **Remove** a connection to cut an agent off at once. The next thing it asks is refused.

The list shows when each key was last used, so you can see that an agent is really connected, and notice a key that
someone else is using.

## Reaching Themis from elsewhere

Themis serves MCP on the same address as the web interface, at `/mcp`. It speaks plain HTTP unless you put it behind
something that adds HTTPS, so only connect agents over a network you trust, or over HTTPS through a reverse proxy.
