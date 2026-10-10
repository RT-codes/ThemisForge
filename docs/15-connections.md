---
title: Connections
group: Using Themis
summary: Connect services like GitHub once, choose one per project, and give it to the agents you trust with it.
---

# Connections

A **connection** is your sign in to an outside service, kept once in Themis so agents can work with that service for you.
GitHub is the first one. Codex (your ChatGPT sign in, see [Connecting Codex](/docs/codex)) is listed beside it, and more
services follow the same steps.

Three steps take a connection from you to an agent:

1. **Connect** the service in **Settings, Connections**. This is yours: nobody else, administrators included, can see or
   use it.
2. **Choose it on the project.** On the project overview, **Connections** lists the services. Press **Choose**, pick one of
   your connections and fill in what the project needs from it (for GitHub, the repository).
3. **Give it to an agent.** In the agent editor, **Connections** has a switch per service. An agent without the switch gets
   nothing, even when the project has the service.

## Connect a service

Open **Settings, Connections**, search the list and press **Connect**. There are two ways in, and both end in the same
kind of connection:

| Way | What it is for |
| --- | --- |
| **Token** (recommended) | You make a token at the service and paste it. You decide exactly what it can access and for how long. |
| **Sign in** | You get a link and a code, approve on any device, and the connection appears. Fastest, but the access it is given is broader than a token you scope yourself. |

Both are kept the same way, so neither is lost when Themis is restarted or upgraded. They are lost if the administrator
changes `THEMIS_SECRET_KEY`: the connection then says it can no longer be read, and you connect again.

**Test** asks the service again whether the credential still works and whose it is. **Disconnect** removes it from Themis
and from every project that used it. To also revoke it at the service, do that in the service's own settings.

## GitHub

The account the token belongs to is the one that acts: commits, issues and pull requests are made as that account.

- **Token**: create a fine-grained token at `github.com/settings/personal-access-tokens`, pick the repositories agents
  should reach, and give it read and write on Contents, Issues and Pull requests.
- **Sign in**: an administrator first creates an OAuth App at `github.com/settings/developers`, switches on *Enable Device
  Flow*, and pastes its client ID under **Settings, Sign in with GitHub**. The client ID is public, not a secret. Until it is
  set, only tokens work.
- **Repository**: on the project you can name the repository (`owner/name`, or a link). Themis checks that the connection
  can see it, and tells the agent about it.

An agent that has GitHub finds `git` and the `gh` command already signed in: `git clone https://github.com/owner/name.git`
works, commits are authored as the account, and `gh issue` and `gh pr` work. This needs the `gh` command in the agent's
image, which the Codex image includes from this version on. Rebuild it with `./themis build-images`.

## How a connection is kept safe

- It is **encrypted at rest** with a key derived from `THEMIS_SECRET_KEY`, and never shown or returned by the API.
- A project can only use connections of its own owner, and only agents that were given the service can use it.
- When a run starts, the secret reaches the cell as an in-memory file, exactly like a stored key, and the cell's start
  script exports it (`GH_TOKEN` and `GITHUB_TOKEN` for GitHub). It is never on a command line. Everything the cell prints
  is scrubbed of its value before it is stored.
- That scrubbing stops accidents, such as printing the environment. It cannot stop an agent that deliberately re-encodes
  the value, so only give a connection to an agent you trust with it.
- A run stops with a note that says why when its connection is missing or can no longer be read, rather than running
  without it.
- If a stored key of the agent has the same variable name as one of its connections, the run stops: rename the key.
