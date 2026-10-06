# ThemisForge

![Themis cover art: a busy control room where AI agents work on projects, tasks, workflows and shared folders.](docs/assets/themis-cover.jpg)

**Put AI agents to work for you, on a computer you control.**

ThemisForge is the project. The app you use is called **Themis**: a place to give AI **agents** (assistants with a role and instructions) jobs to do, now or on a schedule, and to see what they did. It keeps working when you close the browser tab.

For example: *"Every morning, research the news in my field and write me a short summary."*

## What you can do

- **Give agents jobs.** Say what should be done and when: right now, at a set time, or every day.
- **Keep work organised.** Each project has its own agents, tasks and files. Tasks show up on a board, a list or a timeline.
- **Build a small team.** Give each agent a role and instructions. Add **skills** (how-to guides it can follow), **tools** (extra abilities, such as working with files) and **keys** (access to services it needs).
- **Chain steps together.** Draw a **workflow**, like a flowchart, where one agent's result feeds the next step.
- **Share files safely.** Agents hand files to each other through shared folders, and you choose which folders they may read or change.
- **Stay in control.** Read every log and result, cancel anything, and limit how much of the computer's power agents can use.

## Is it safe?

Every job runs in its own sealed, throwaway "box" (a Docker container). It only sees the folders you approved, and it is deleted when the job ends. Each box has limits on power, memory and time.

The box is the safety fence, so agents work inside it without stopping to ask permission. Only share folders you are comfortable with them changing. Themis does not cap AI spending yet (planned): agents use your own ChatGPT plan's allowance.

## Install

**Linux (Ubuntu or Debian).** You need a computer or virtual machine you control, with internet and a normal user account that has admin (`sudo`) rights. The installer adds what is missing, including Docker.

```bash
git clone https://github.com/RT-codes/ThemisForge.git
cd ThemisForge
./themis install
```

Then open **http://127.0.0.1:8000** and create your account. Themis starts by itself whenever the machine does. To preview the installer first, add `--dry-run`; `./themis doctor` checks that everything works.

**To run agents** (using your ChatGPT account through Codex) you also need to:

1. Install the [Codex command-line tool](https://github.com/openai/codex) on the same machine. The installer does not do this.
2. Run `./themis build-images` once. It prepares the box agents work in (a few minutes, about 1 GB).
3. In Themis, open **Settings** and press **Connect Codex**.

Installing on a server you reach from elsewhere? By default Themis only answers on the machine itself. The [deployment guide](docs/08-operations.md) explains how to open it up safely.

**Windows: coming soon.** We have not tested Themis on Windows yet, so there are no instructions to give. Other systems, such as macOS, have not been tested either.

## Once it is running

1. Create your account (the first account is the administrator; everyone else joins by invitation).
2. Create a project.
3. Connect your ChatGPT account so agents can think.
4. Create an agent, give it a task, and run it now or on a schedule.
5. Watch it work and read the result.

**The step-by-step guide is inside the app.** Click **Docs** in the sidebar, or open **http://localhost:8000/docs** (no sign-in needed). It also covers workflows, shared folders, settings and troubleshooting.

## Coming soon

Windows support, and more agent engines: Codex is the one supported today, with Claude and OpenRouter to follow. See the [roadmap](docs/11-roadmap.md). ThemisForge is under active development.

Want to help build it? See [CONTRIBUTING.md](CONTRIBUTING.md).
