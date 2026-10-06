---
title: Settings
group: Running it
summary: Docker connection, cell defaults, time zone and stored keys.
---

# Settings

The **Settings** page has two parts. **Your account** holds your own connections (see [Connecting Codex](/docs/codex)) and
everyone can use it. **Administration** controls how this installation runs, and only the administrator sees it.

Every section folds away, and a folded section says in one line what is inside. ThemisForge remembers which ones you
left open. Change something and a bar slides in at the bottom with **Discard** and **Save changes**.

## Docker

Cells are Docker containers, so ThemisForge needs to reach a Docker engine. The Docker section runs a live check and
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
machine than the one hosting ThemisForge. Note that cell workspaces are mounted from the ThemisForge machine, so
a remote host needs the same paths available.

> [!WARNING]
> Access to Docker is effectively root access on that machine. Point ThemisForge only at hosts you trust.

## Cells

Defaults for every cell: image, CPUs, memory, time limit and how many run at once. See
[Cells and workspaces](/docs/cells). Saving applies the change to the next cell that starts.

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

Keys are stored and managed here, but are **not yet injected into cells**. That arrives with agents.

## Insecure secret key notice

If `THEMIS_SECRET_KEY` is still the development default, Settings shows a warning. Sessions could be forged and stored
keys are weakly protected. The installer generates a real key for you. On a development machine you can ignore the
notice.
