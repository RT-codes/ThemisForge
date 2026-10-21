---
title: Settings
group: Running it
summary: Docker connection, resource budget, cell defaults, time zone and stored keys.
---

# Settings

The **Settings** page has two parts. **Your account** holds your own connections (see [Connections](/docs/connections) and
[Connecting Codex](/docs/codex)) and everyone can use it. **Administration** controls how this installation runs, and only the administrator sees it.

Every section folds away, and a folded section says in one line what is inside. Themis remembers which ones you
left open. Change something and a bar slides in at the bottom with **Discard** and **Save changes**.

## Docker

Cells are Docker containers, so Themis needs to reach a Docker engine. The Docker section runs a live check and
reports one of three things:

- **Connected**: shows the Docker version, the host, the operating system, CPUs and memory.
- **Not reachable**: the daemon is down, or this user is not allowed to use it.
- **Not installed**: the `docker` command is missing.

Each failure comes with a hint on how to fix it.

### Docker host

Leave **Docker host** empty to use the Docker on this machine. To use another machine, enter one of:

| Form | Example |
| --- | --- |
| SSH | `ssh://user@host` |
| TCP | `tcp://host:2376` |
| Unix socket | `unix:///var/run/docker.sock` |

Press **Test** to check a value before saving it. This is how a project can run its cells on a different, stronger
machine than the one hosting Themis. Note that cell work folders are mounted from the Themis machine, so
a remote host needs the same paths available.

> [!WARNING]
> Access to Docker is effectively root access on that machine. Point Themis only at hosts you trust.

## Resources

How much of the machine all running cells together may use. The section shows what the machine has, as the Docker daemon
sees it (which can be another machine), and the free space on the drive Themis keeps its data on. Below that you set
the **budget**: CPUs and memory for all cells together.

- The bars show how much of the machine the budget takes. A budget larger than the machine is marked, because cells
  would then compete for what is not there.
- **Fits N cells** tells you how many cells of the default size (see below) run at the same time with this budget.
- **Use recommended** fills in a budget that leaves the machine room for itself: a CPU (or a fifth of them, whichever is
  more) and a quarter of the memory.
- If not even one default cell fits, the section opens by itself and tasks fail with a note until you raise the budget.

Before the budget existed, Settings limited the number of cells. An existing installation keeps its behaviour: the old
number is turned into the same number of cells of the configured size.

## Cells

Defaults for every cell: image, CPUs, memory, time limit and how long working folders are kept. See
[Cells and work folders](/docs/cells). Saving applies the change to the next cell that starts.

## Claude Code agents

The image, model and reasoning effort tasks use when they run with a Claude Code agent and the agent does not choose its
own. Build the default image with `./themis build-images`. The account comes from your
[Claude Code connection](/docs/claude-code).

## Cell package

What Themis itself adds to every Codex run, on top of the agent's own instructions, so you can read it, change it or switch
it off. Administrators only. Applies to the next cell that starts.

- **Rules**: a few lines in every prompt. They say the container has no root and no package manager, and that an agent that
  cannot do its task must write why to `/cell/blocked.md` and stop. That is what makes a ticket fail with a reason and a
  "what to do". Switched off, agents get none of this.
- **Skill `themis-cell`**: a map of the agent's computer (what is installed, how to use the browser). Only its one-line
  description is in the agent's context until the skill is needed. It is mounted read only in every cell, so an agent cannot
  change it. It describes the default [Codex image](/docs/codex); edit it if your agents use another image. It must keep
  the name `themis-cell` and a description.
- **Retry when the model provider is busy**: seconds to wait before each new try, for errors such as "model is at
  capacity" (30, 90, 180 by default, so three retries). Empty means never retry.

A text you leave as it is stays the built-in one, which improves with new versions of Themis; only what you change is
stored. **Use the built-in text** takes an edit away again. Each agent's Skills tab lists `themis-cell` first, locked: open it to read the skill and the rules exactly as agents get them (any user can read it, only an administrator can change it).

## Automation

- **Wait before a Ready task starts**: a task starts this long after it was moved to Ready or its last run ended, and a
  workflow starts for a task no sooner than this after the last one did. 5 seconds by default; 0 starts right away.
- **Most automatic moves of one task in a row**: how many times workflows may move or make the same task before they are
  stopped (10 by default). Both can be set per project (the project's Settings, **Cells and automation**) and per task. See
  [the automation guard](/docs/workflows#the-automation-guard).

## Mount roots

The folders on this machine that agents may be given. Projects can only add a folder as a [shared folder](/docs/cells#shared-folders)
if it is inside one approved here, and an approved folder is read only unless you switch on **Allow writing** for it.

- Everything inside an approved folder is covered, including sub folders. Approving the whole disk (`/`) is not allowed.
- A link that leads out of an approved folder does not count: the real location is what is checked.
- Themis's own data folder, database and configuration can never be mounted, nor a folder that contains them.
- Taking an approval away does not delete anything. Volumes that relied on it are marked in the project, and runs that
  would use them fail with a note until you approve the folder again.

> [!WARNING]
> Agents run unattended. A folder they may write to can have files changed or deleted, with no undo. Approve only what you
> are fine with that for.

## Updates

The **Updates** section says whether a newer Themis exists. A minute after Themis starts, and then once a day, it asks
GitHub for the list of releases (one plain request; nothing about you, your projects or this machine is sent, and
nothing is ever installed by itself). When there is a newer one, administrators see a notice at the top of every page
and in this section, with a link to what is new. Close the notice to hide that version until the next release.

- **Look for new versions** switches the check off. You can still look yourself with `themis upgrade --check`.
- **Which versions** chooses *Stable only* (the default) or *Stable and beta*, which also offers pre-releases.
- The refresh button checks right now.

The notice never upgrades anything: run `themis upgrade` on the server, which backs up first and goes back by itself if
the new version does not start (see [Install and operations](/docs/operations#upgrading)). A development checkout is
never told to upgrade, since it is updated with `git pull`.

## Schedules

The **time zone** used to evaluate recurring schedules. Pick the zone where you want "every morning" to happen. The
button next to the field offers the zone of your current browser. See [Scheduling](/docs/scheduling).

## Tool registry

Under **Connections**, administrators have **Tool registry**: a way into the official MCP registry from Settings, for
finding tools without going through a project first. It opens the same browser as **Add from registry** on a project (see
[Agents](/docs/agents)). Tools belong to a project, so after you pick one Themis asks which project it is for and then
shows the usual tool form with the fields filled in.

## Tool sign ins

Under **Connections**, **Tool sign ins** lists your sign ins to hosted tools that ask for one, such as Notion, with when
each token is next renewed, and signs out of them. Administrators also have **Sign in rules**, saved with the Save bar:

| Setting | What it does |
| --- | --- |
| **Renew early by** | A token must still last this long on top of a run's time limit when the run starts, or it is renewed first. |
| **Assumed token life** | How long a token is taken to last when the service does not say. Services normally do, and their answer wins. |
| **Keep unused sign ins alive** | Renews a sign in nobody used for this many days, so the service does not let it lapse. 0 switches it off. |
| **A sign in waits for** | How long a started sign in waits for you to approve on the service's page. |
| **Wait for a service** | How long each call to a service may take. |
| **Name on the consent page** | What the service shows as the app asking for access. |
| **Themis' public address** | Where the service sends you back after you approve. Empty uses the address the page was opened on. Set it behind a reverse proxy. |

See [Agents](/docs/agents#tools-that-sign-in) for how a tool signs in.

## Keys

Store credentials that are shared by the whole installation, such as a model provider's API key or a key for a tool. They
belong to the administrator. Your own sign ins to services like GitHub are [connections](/docs/connections) instead. Keys are:

- **encrypted at rest** with a key derived from `THEMIS_SECRET_KEY`,
- **masked** in the interface: after saving you only see the last four characters,
- **deletable** at any time.

> [!WARNING]
> If you change `THEMIS_SECRET_KEY`, previously stored keys can no longer be read. Add them again after changing it.

An administrator can give a key to an agent (the **Keys** part of the [agent page](/docs/agents#keys)) or to a tool. Deleting a
key takes it away from every agent and tool that had it. The list of key names (never their values) is visible to every
signed in user, because they need it to see what an agent has.

## Insecure secret key notice

If `THEMIS_SECRET_KEY` is still the development default, Settings shows a warning. Sessions could be forged and stored
keys are weakly protected. The installer generates a real key for you. On a development machine you can ignore the
notice.
