---
title: Connecting Claude Code
group: Using Themis
summary: Use your Claude subscription or an API key so agents can run on Claude Code, next to Codex.
---

# Connecting Claude Code

Agents can run on **Claude Code** as well as [Codex](/docs/codex). The two work the same way for you: pick the harness
on the agent (or on a task, a webhook or a workflow step), and Themis runs it in a throwaway cell with the agent's
instructions, skills, tools and keys. Mixing them is fine: one workflow can have a Codex step followed by a Claude Code
step, and the files they leave behind are shared like any other.

## Connect

1. Run `claude setup-token` in a terminal where Claude Code is installed, sign in, and copy the token it prints (it
   starts with `sk-ant-oat`). It uses your Claude plan and lasts a year.
2. Open **Settings, Connections** and press **Connect** on Claude Code. Paste the token.

An **Anthropic API key** (starts with `sk-ant-api`) works too. Themis checks it with Anthropic before saving it. A
subscription token cannot be checked ahead of time, so a wrong one shows up as a login error in the first run.

Every user connects their own account. A run signs in with the account of the project's owner, so nothing is chosen per
project or per agent. With both a subscription token and an API key connected, the one connected last is used. The
attempt records which it was: **subscription** runs draw on your plan's usage limits, **API** runs are billed per token.

Requires a real `THEMIS_SECRET_KEY`, like every stored credential.

## Image, model and effort

`./themis build-images` builds the cell image for each harness from the same Dockerfile (`themisforge/cell-claude`
next to `themisforge/cell-codex`), so the tools around the agent are the same. Under **Settings, Claude Code agents** you
set the image, the default model and the default reasoning effort; an agent can choose its own model and effort, and a
workflow step can override them for one run.

## How a run works

Themis starts the cell, hands over the prompt, and runs `claude -p` with its permission prompts switched off (the
container is the sandbox, as with Codex). The log shows what the agent said and thought, each command and tool call, and
what they printed; the final message is stored as the run's **result**. A run that Claude Code ends with an error is a
failed run. Tokens are recorded per attempt, retries included.

- **Skills** are read only at `/workspace/.claude/skills`, together with the built-in `themis-cell` skill.
- **Tools (MCP)** are handed over as Claude Code's own configuration. A tool that needs a key or a sign in gets it the
  same way as for Codex, and the secret is not written into the configuration file in clear text for web tools.
- If the API is overloaded the run is started again after the waits set in **Settings, Cell package**. A refused login
  is not retried: the attempt says so and asks you to connect again.

## Good to know

- Claude Code's token does not rotate, so unlike Codex there is nothing to refresh and runs of the same account do not
  have to take turns. They all draw on the same usage limits, so many parallel runs use a plan up quickly.
- Disconnecting the account makes the agent's next runs fail with a note to connect it again.
