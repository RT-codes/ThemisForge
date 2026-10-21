---
title: Webhooks
group: Using Themis
summary: Let other programs make tasks: a shop, GitHub, a form or your own script posts a message and Themis does the work.
---

# Webhooks

A **webhook** is an address that other programs can send a message to. Every message makes a **task** in your project,
set up the way you chose. Until now work started from the clock or from you. With a webhook it can start from the world:

- a shop sends "new order 1042" and an agent writes the packing slip,
- GitHub sends "issue opened" and an agent looks into it,
- a contact form sends a message and an agent drafts the reply for you to approve,
- a script of your own starts a job with one line.

You make webhooks in the project's **Settings**, under **Webhooks**.

## Who decides what

A message comes from outside, so it is trusted with as little as possible.

| The sender decides | You decide, once, on the webhook |
| --- | --- |
| What the message says. | The board and status the task lands in. |
| | Which agent, or which workflows, run it. |
| | Whether a finished task waits in Review. |
| | How the message becomes the title and the text of the task. |
| | Which messages count at all. |

Nothing in a message can change the second column. A message that says `"status": "ready"`, names an agent or asks for a
schedule is simply text: the task still lands where the webhook says, runs the way the webhook says, and has no schedule.
Webhook tasks are made like tasks you make by hand, so the automation guard, **Halt** and workflows that watch a status
all treat them the same.

## Make one

Press **New webhook** and choose:

- **Name.** For you; it also becomes the task's title when a message has none.
- **Where its tasks land.** A board and a status. The **Backlog** is the safe choice: the task waits until you move it
  on. Choose **Ready** to run every message at once, or a status of your own that a workflow watches, to send the task
  into a workflow without running it by itself first.
- **Run with.** An agent, a Codex or Claude Code run, or a list of workflows to play one after the other, exactly as on a task.
- **What a message becomes** and **Only when**, below.

After you make it, Themis shows the **address** once. Copy it and give it to whatever should send messages. Only the end
of it is kept afterwards, so a lost address cannot be shown again: make a new one with **New address**, which ends the
old one at once.

> **Treat the address like a password.** Anyone who has it can make tasks in this project, up to 60 messages a minute.
> The text of a message goes into the task an agent works on, so think about who can send to a webhook that runs an agent
> by itself. A public repository lets strangers open issues. For messages you do not control, land the task in the
> Backlog or in Review and look at it before an agent with access to anything valuable works on it.

## What a message becomes

A message can be JSON or a form; plain text works too. Out of the box:

- the **title** is the message's own `title`, else the webhook's name,
- the **description** is the message's own `description`, else the whole message, so nothing that arrived is lost.

So this already works with no setup (the address is the one Themis showed you):

```
curl -X POST <address> -H "content-type: application/json" -d '{"title": "Make 5 sword icons", "description": "Pixel art, 32x32"}'
```

Real services send their own shape, so the title and the description can be **templates**. Put `{{name}}` where a value of the
message belongs. A dotted path goes inside objects, and a number goes into a list:

| Write | It gives |
| --- | --- |
| `{{issue.title}}` | The `title` inside `issue`. |
| `{{commits.0.message}}` | The message of the first commit in the list. |
| `{{_event}}` | What the sender called the event (`issues`, `push`...), from the headers GitHub, GitLab and Bitbucket send. |
| `{{_raw}}` | The whole message as it arrived. |

A value that is not there is empty. An object or a list is written out as JSON, which an agent can read. A title is one
line and at most 200 characters; a description at most 20,000.

For GitHub issues:

```
Title:        {{repository.name}}: {{issue.title}} (#{{issue.number}})
Description:  {{issue.user.login}} opened {{issue.html_url}}

              {{issue.body}}
Only when:    action is opened
```

**Fill in the GitHub issue example** in the form puts exactly this in.

### Only when

A service often sends several kinds of message to one address: GitHub says "opened", "edited", "labeled", "closed" and
more for the same issue. **Only when** lists rules, and a message makes a task only when every rule holds. A rule names a
value and what it may be (several allowed, separated by commas). Leave the values out to only ask that the value is there.
A message that does not match is answered normally, makes no task, and shows in the log as **No task** with the reason.

## Set it up with GitHub

In the repository, **Settings, Webhooks, Add webhook**:

1. **Payload URL**: the address Themis showed you. GitHub must be able to reach it, which means Themis needs a public
   address (a server, or a tunnel while you try it on your own computer).
2. **Content type**: `application/json`. The form type works too.
3. **Which events**: choose the ones you want, such as *Issues*. Rules in Themis can narrow them further.

GitHub sends a **ping** when the webhook is made. Themis answers it and makes no task. GitHub then lists every
delivery with Themis's answer, and can send one again.

## What arrived

Open a webhook and its **Messages** tab shows the last 50 messages, newest first, each with what became of it:

| Outcome | Meaning |
| --- | --- |
| **Task made** | A task was made. |
| **No task** | The message did not match a rule, or it was the sender's ping. |
| **Repeat** | The sender sent a delivery it had already sent (it retries when it thinks we did not answer). GitHub, GitLab and anything that sends an `Idempotency-Key` are recognised, and make one task. |
| **Refused** | The webhook is switched off, its board is gone, or the task could not be made. The reason is on the line. |

Open a line to read the message itself. That is the quickest way to write a template: let the service send one
message, read it here and take the paths from it. **Use as the test message** copies it into the box at the top, where
you can **Send** it again after changing the setup. A test message makes a real task, like any other.

## Good to know

- **A halted project still receives messages.** The task waits like any task in a halted project, and starts when you resume.
- **Switch a webhook off** with its switch in the list. Messages are refused, and nothing is made.
- **A board or status that is deleted.** Deleting a custom status moves the webhook to where its tasks went. Deleting a
  board leaves the webhook refusing messages (it says so in the list) until you choose another board.
- **Limits.** A message can be 1 MB, and a webhook accepts 60 a minute; more get the answer "too many", which senders
  retry later.
- **What is stored.** The address as a hash, the settings, and the last 50 messages with their text. Deleting a webhook
  deletes its log; the tasks it made stay.
- **Not yet.** Checking the signature GitHub adds to a message, setting task properties from a message, and starting a
  workflow directly instead of through a task.
