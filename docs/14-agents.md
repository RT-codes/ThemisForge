---
title: Agents
group: Using Themis
summary: Configure who does the work in a project: role, instructions, harness, model, cell and folders.
---

# Agents

An **agent** is a configured worker of one project. It says who the worker is, what it was told, how it runs and what it
can reach, so a task or a workflow step only has to say *which* agent should do it.

The project's **Settings** also lists its agents under **Agents**: click one to open it.

Open **Agents** under a project in the sidebar. The list is on the left and the first agent is already shown on the right,
as an overview of who it is, what it was told and what it has. Picking an agent only shows it; press **Edit** to change
it, or **New agent** at the top to make one. A project starts with none, and can have as many as it needs. In the editor,
**Save changes** saves the settings, **Done** goes back to the overview, and leaving with unsaved changes asks first.

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
| **Folders** | The [shared folders](/docs/cells#shared-folders) mounted in its work folder, and whether it may write to them. |
| **Connections** | The services it may act on, like GitHub, through the connection the project chose. See [Connections](/docs/connections). |
| **Skills** | Guides it reads when a task calls for them (see below). |
| **Tools** | Extra tools it can use, as MCP servers (see below). |
| **Keys** | Stored keys its commands can use (see below). |

When the agent runs, its prompt starts with who it is and its instructions, then the task, then a list of the folders it
has and whether each is read only. The project's `shared` folder is always among them.

## The config folder

Everything that sets an agent up is kept as files in the project's **config folder**, which is the `config` tab on the
**Files** page:

```
config/
  agents/<name>/agent.md     the agent: its settings between two --- lines, then its instructions (`connections:` lists its services)
  skills/<name>/SKILL.md     a skill (and anything else you put in its folder)
  mcp/<name>.yaml            a tool
```

The files are the truth: change one and the agent changes, change the agent in the editor and its file is written. They
refer to folders, skills, tools and keys by name, never by secret value. Some things to know:

- A file is **checked when you save it** on the Files page or in the editor. One that could not work (a skill that does not
  exist, a missing `---` line, a typo in a setting name) is refused with the reason, and nothing is stored.
- A file that is broken on disk anyway keeps the agent's last good version and shows a warning on the agent. The agent will
  not run until it is fixed (a task says why), so a typo never quietly changes what an agent does.
- A file that is deleted does not delete the agent: it is flagged, and can be deleted from the editor. Moving an agent's
  folder keeps the agent (and the tasks and workflows that use it).
- Only the project's owner can see and change it. It is **never mounted** into a cell, so an agent cannot change its own
  instructions, skills or tools. Only an administrator can put a key in a file, as in the editor.
- The three folders `agents`, `skills` and `mcp` keep their names. Your own notes can sit next to the files.

## Skills

A **skill** is a folder with a `SKILL.md` file: a name and a description between two `---` lines, then instructions. The
description is how an agent decides when a skill applies, so say *when* to use it.

In the agent editor, **Skills** lists every skill of the project with a switch for the ones this agent has. Pick a skill
to read it beside the list, edit it and save it on the spot (it is the same preview and editor as on the Files page), or
press **New skill**. The switches are saved with the agent; the files are saved as you edit them. Skills are shared:
editing one changes it for every agent that has it. The project's Settings lists them too, under **Skills**.

- A skill folder can hold more than `SKILL.md`: scripts or reference files are given to the agent too, and show as tabs
  above the file in the editor.
- Each run gets its own copy of only the skills the agent has, mounted **read only** at `/workspace/.agents/skills`, where
  Codex looks for them. An agent cannot change a skill, and does not see the ones it was not given.
- Deleting a skill takes it away from the agents that had it, and rewrites their files.

## Tools

A **tool** is an MCP server that gives an agent more to work with, such as a file system, a search service or a database.
In the agent editor, **Tools** lists every tool of the project with a switch for the ones this agent has. Pick one to see
and change it, or press **New tool**. They are also listed under **Tools** in the project's Settings.

- **With a command**: type the command line (`npx -y @modelcontextprotocol/server-filesystem /workspace`). It is started
  inside the agent's container, so the image must have what it runs. Under **Settings** you can add plain settings as
  environment variables, and an administrator can add keys.
- **At a web address**: the URL of a server on the web. Under **Access** it is open, takes a key sent as a bearer token,
  or asks you to **sign in with the service**. See [Tools that sign in](#tools-that-sign-in) below.
- A tool has a **description** for people, and a **Test connection** button. For a web address the test connects, starts a
  session and lists what the server offers. For a command it looks the command up in the image agents run in (it does not
  start it: that happens when an agent runs). The last result is remembered and shown as a coloured dot. A key is only
  sent by a test when an administrator runs it. A tool that signs in is tested with your sign in.

### Tools that sign in

Hosted tools such as Notion do not take a key: they ask you to sign in on their own page and choose what Themis may reach
(for Notion, which pages). Set **Access** to *Sign in with the service* and press **Sign in** on the tool in the project's
**Tools**. The service's page opens, you approve, and you land back on the project.

- **It is yours.** Runs of a project use the sign in of the project's owner. It is found by the server's address, so
  signing in once serves every tool of yours that points at that server. Settings, **Tool sign ins** lists them and signs
  out of one.
- **Before a run, not during.** A run needs a token that outlasts it. Themis renews the token first when it would not, and
  hands the cell only that short lived token. The long lived part stays on the host, because services rotate it on every
  use. A tool that is not signed in stops the run with a note saying so, before any cell starts.
- **Kept alive.** Services end a sign in that sits unused (Notion after 30 days), so Themis renews unused ones on a
  schedule. If the service ends one anyway, the tool shows *Needs a new sign in* and the run says so.
- **Pick again.** **Sign in again** opens the service's page afresh, which is also how to change which pages it may reach.
- **Sign out** forgets it in Themis. To withdraw the access itself, use the service's own settings.
- **Adding from the registry.** Themis asks a hosted server whether it wants a sign in, so the form opens already set up
  for it.

The numbers (how early a token is renewed, how long a token is assumed to last, how long unused sign ins are kept alive)
are administrator settings under **Settings, Tool sign ins**. What a single service needs differently, such as a scope or
a client id registered by hand, is in `backend/app/mcp_auth/servers.yaml`, read on every sign in. The standard way MCP
servers sign people in is built in; another way of signing in is added as one class (`backend/app/mcp_auth/scheme.py`
describes what it must do).

### Adding a tool from the MCP registry

Administrators can press **Add from registry** next to **New tool**, or **Browse the registry** under **Settings, Tool
registry**, to browse the official MCP registry (registry.modelcontextprotocol.io) instead of typing a tool in. It lists
tens of thousands of tools that anyone has published. From Settings Themis asks which project the tool is for, because a
tool always belongs to one project (keys are shared between projects); from a project it is added there.

- **Browsing.** Categories are on the left (with how many tools match your search in each), **Featured** is the short
  list we picked, and the search box looks through names and descriptions. **Sort** by Recommended, Most downloaded,
  Recently updated or Name. **Runnable only** hides what this project's image cannot start.
- **Recommended** is not popularity, because the registry has none. It puts first what can run here, comes from a
  publisher that proved a domain it owns, is filled in, was updated recently and (for npm packages) is downloaded a lot,
  and it puts publishers that list hundreds of near-identical tools below the rest. **Most downloaded** is npm's
  downloads in the last month, so only npm packages have a number.
- **Icons** are the one the publisher declared, else the GitHub avatar of the owner, else the tool's initials. Your
  browser loads them from those hosts as you scroll, and tells them nothing about the page.
- **A copy kept on this machine.** The registry's own search is slow, so Themis reads its whole listing once (a few
  minutes, in the background, the first time somebody opens the browser) into a file under the data folder
  (`cache/mcp-registry.json`). After that it asks only for what changed, at most once a day, or when you press **Update
  now**. npm download counts are fetched from npm in the background, at most once a week for each package.
- **What cannot run.** Every tool is listed. The ones Themis cannot run yet are greyed out, and picking one says why: it is
  a container image, needs .NET, only offers the older SSE connection, needs custom headers, or the cell image lacks the
  program that starts it (`npx` for npm packages, `uvx` for Python packages, both in the Codex image).
- **Adding.** A tool that can run asks for what it needs: required settings, and a stored key for anything secret. The
  key's value is never typed here. It then opens the normal tool form, filled in, and nothing exists until you press
  **Create tool**. Packages are pinned to the version the registry lists.
- **Take care.** Anyone can publish to the registry and nobody vets what is listed. A package runs inside the cell with
  the agent's access to its folders and any key you give it, and a hosted address receives everything the agent sends it.
  Some hosted tools want you to sign in with a browser. The registry does not say which, so Themis asks the server when
  you pick one and opens the form set up to sign in (see [Tools that sign in](#tools-that-sign-in)).

Two files, both edited by hand, change what the browser shows. They are read again whenever they change, no restart
needed:

- `backend/app/featured_tools.yaml`: the featured tools, as registry names with an optional note.
- `backend/app/registry_categories.yaml`: the categories and the keywords that put a tool in one. A tool goes where it
  matches most keywords (a name counts three times a description).

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
- Removing a shared folder, skill, tool or key also removes it from the agents that had it, and their files are rewritten.
- Agent settings are saved with the **Save changes** button; leaving the editor without saving asks first. Skill and tool
  files edited inside the editor are saved on their own.
