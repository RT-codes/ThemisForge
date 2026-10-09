---
title: Settings
group: Running it
summary: Docker connection, resource budget, cell defaults, time zone and stored keys.
---

# Settings

The **Settings** page has two parts. **Your account** holds your own connections (see [Connecting Codex](/docs/codex)) and
everyone can use it. **Administration** controls how this installation runs, and only the administrator sees it.

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

## Keys and connections

Store credentials for model providers and tools (Anthropic, OpenAI, Google, GitHub or custom). They are:

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
