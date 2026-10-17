---
title: Notifications
group: Using Themis
summary: Get a message in a chat when a task fails or something waits for you, so you do not have to keep the app open.
---

# Notifications

Themis can tell you when something happens, in a chat you already look at. Work then runs on its own, and your phone
buzzes only when it needs you.

You connect a chat in the project's **Settings**, under **Notifications**. Each project has its own list, and a project
can have several (a channel for you, a channel for the team).

## What you hear about

Each notification listens for the events you tick:

| Event | When it is sent | On by default |
| --- | --- | --- |
| **A task failed** | A task ended in a failure, or could not start at all. The message carries the reason. | Yes |
| **Something waits for me** | A task is in **Review**, or a workflow run is parked at an [approval gate](/docs/workflows). | Yes |
| **A task finished** | A task completed. This is chatty on a busy project, so it is off until you ask for it. | No |

A few rules keep it quiet:

- The steps inside a workflow do not speak for themselves. The task that plays the workflow is the one you hear about.
- A task you cancelled yourself says nothing.
- The same event for the same task is sent **once in five minutes** per notification. A recurring task that fails every
  minute tells you once, not sixty times.
- A notification that is switched off hears nothing.

## Discord

Discord needs no bot. A channel can give out a **webhook address** that anyone holding it can post to:

1. In Discord, open the channel's settings, then **Integrations**, then **Webhooks**, then **New Webhook**.
2. Copy the webhook URL. It starts with `https://discord.com/api/webhooks/`.
3. In Themis, choose **New** under Notifications, paste it and tick the events you want.
4. Press **Send a test** to see a message land in the channel.

For a place of your own, make a small Discord server with one channel and put the Discord app on your phone.

## Keeping the address private

The address is a secret: whoever has it can post in your channel. Themis stores it encrypted, like a key, and never
shows it again. After saving you only see its last few characters. To change it, type a new one over it. Task titles
cannot ping `@everyone`: Themis sends the message with mentions switched off.

## When a message does not arrive

Sending never holds up your work. If the chat cannot be reached, the task carries on and the notification shows
**Last message failed** with the reason (for example, that Discord answered with status 404 because the webhook was
deleted). The next event tries again. **Send a test** tells you straight away whether the address works.

## More chats

Each chat service is one small piece in Themis, so others (Telegram, a push service such as ntfy) can be added without
changing how this screen works. See the [roadmap](/docs/roadmap).
