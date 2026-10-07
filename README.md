# ThemisForge

![Themis cover art: a busy control room where AI agents work on projects, tasks, workflows and shared folders.](docs/assets/themis-cover.jpg)

**Put AI agents to work for you, on a computer you control.**

ThemisForge is the project. The app you use is called **Themis**: a place to give AI **agents** (assistants with a role and instructions) jobs to do, now or on a schedule, and to see what they did. It keeps working when you close the browser tab.

For example: *"Every morning, research the news in my field and write me a short summary."*

> **Early development (version 0.x).** Themis works, but it is young: things still change, and rough edges remain. Back up what matters (`themis backup`), and tell us what you run into in the [issues](https://github.com/RT-codes/ThemisForge/issues).

## What you can do

- **Give agents jobs.** Say what should be done and when: right now, at a set time, or every day.
- **Keep work organised.** Each project has its own agents, tasks and files. Tasks show up on a board, a list or a timeline.
- **Build a small team.** Give each agent a role and instructions. Add **skills** (how-to guides it can follow), **tools** (extra abilities, such as working with files) and **keys** (access to services it needs). Agents, skills and tools are plain files in the project's config folder that you can read and edit.
- **Chain steps together.** Draw a **workflow**, like a flowchart, where one agent's result feeds the next step.
- **Share files safely.** Agents hand files to each other through shared folders, and you choose which folders they may read or change.
- **Stay in control.** Read every log and result, cancel anything, and limit how much of the computer's power agents can use.

## Is it safe?

Every job runs in its own sealed, throwaway "box" (a Docker container). It only sees the folders you approved, and it is deleted when the job ends. Each box has limits on power, memory and time.

The box is the safety fence, so agents work inside it without stopping to ask permission. Only share folders you are comfortable with them changing. Themis does not cap AI spending yet (planned): agents use your own ChatGPT plan's allowance.

## Install

**Linux.** You need a computer or virtual machine you control, with internet and a normal user account that has admin (`sudo`) rights. One command installs the newest release, checks that Docker works (and offers to install it if it is missing), and starts Themis as a service:

```bash
curl -fsSL https://github.com/RT-codes/ThemisForge/releases/latest/download/install.sh | sh
```

Then open **http://127.0.0.1:8000** and create your account. Themis starts by itself whenever the machine does. `themis doctor` checks that everything works, and `themis upgrade` moves to a newer version (it backs up first and goes back by itself if something fails). More in the [install and operations guide](docs/08-operations.md).

Docker Engine 24 or newer is required, with Linux containers (Themis checks this every time it starts).

**To run agents** (using your ChatGPT account through Codex):

1. Open **Settings** in Themis and press **Connect Codex**. You sign in once; nothing else needs installing.
2. Create an agent, give it a task, and run it.

Installing on a server you reach from elsewhere? By default Themis only answers on the machine itself. The [deployment guide](docs/08-operations.md) explains how to open it up safely.

**Windows 10 or 11 (new, please report problems).** Open **PowerShell** (Start menu, type "PowerShell"; not "as administrator") and run:

```powershell
irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1 | iex
```

(`irm` is a PowerShell command, so it does not work in Command Prompt. From Command Prompt use `powershell -NoProfile -Command "irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1 | iex"`.)

It needs [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with Linux containers (the installer checks, and offers to install it with winget if it is missing). Docker Desktop in turn needs **hardware virtualization** turned on in the computer's BIOS: most PCs have it on, and if yours does not, the installer tells you before it installs anything and shows how to switch it on (a one-time setting). Themis installs for your own account without administrator rights, and starts Themis whenever you log in. Windows support is new: it is tested automatically, but on far fewer real computers than Linux. **macOS** is on the list after that.

## Once it is running

1. Create your account (the first account is the administrator; everyone else joins by invitation).
2. Create a project.
3. Connect your ChatGPT account so agents can think.
4. Create an agent, give it a task, and run it now or on a schedule.
5. Watch it work and read the result.

**The step-by-step guide is inside the app.** Click **Docs** in the sidebar, or open **http://localhost:8000/docs** (no sign-in needed). It also covers workflows, shared folders, settings and troubleshooting.

## Coming soon

More agent engines: Codex is the one supported today, with Claude and OpenRouter to follow. See the [roadmap](docs/11-roadmap.md). ThemisForge is under active development.

Want to help build it? See [CONTRIBUTING.md](CONTRIBUTING.md). Found a security problem? Please read [SECURITY.md](SECURITY.md) before you report it.

## License

ThemisForge is open source under the [Apache License 2.0](LICENSE): free to use, change and share, including commercially.
