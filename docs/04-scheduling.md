---
title: Scheduling
group: Using Themis
summary: Manual, one-off and repeating schedules, time zones and what happens when things are late.
---

# Scheduling

Themis has one always-on scheduler. About every three seconds it looks for tasks that are **Ready** and **due**,
and starts a cell for each, as long as it fits the [resource budget](/docs/settings#resources).

## Three kinds of schedule

| Kind | Behaviour |
| --- | --- |
| **Manual** | No schedule. Runs when the task is Ready and a cell is free, or when you press **Run now**. |
| **Once** | Runs a single time at a date and time you choose (shown in your local time). |
| **Recurring** | Repeats on a schedule you pick, for as long as the task is Ready. |

## Repeating

Choose how a task repeats in the task editor:

| Repeat | Example |
| --- | --- |
| **Every day** | Every day at 09:00 |
| **Every weekday** | Monday to Friday at 18:30 |
| **Every week on chosen days** | Every Monday and Thursday at 07:00 |
| **Every month on a day** | The 1st of every month at 09:00 (days 1 to 28, so every month has one) |
| **Every hour** | At a minute past the hour of your choice |
| **Every few minutes** | Every 5, 10, 15, 20 or 30 minutes |

The task card and the task list show the schedule in words, like "Every weekday at 18:30".

> [!NOTE]
> Under the hood a repeating schedule is stored as a cron expression, which is why a task created through the API can
> carry one the editor has no wording for. Such a task is shown as a **custom schedule**, keeps running as before, and
> is replaced as soon as you pick a repeat in the editor.

## Time zones

Recurring schedules are evaluated in the **time zone set on the Settings page**, not in UTC and not in your browser's
zone. "Every day at 09:00" therefore means 09:00 in that zone, including across daylight saving changes. The task editor
names the zone next to the time so there is no guessing.

One-off times are picked in your browser's local time and stored as an exact moment.

## Pausing

A recurring task only runs while it is in **Ready**. Move it to **Inbox** to pause it and back to **Ready** to resume.
Resuming does not replay what was missed: the next occurrence is computed from the moment you resume.

## Late and missed runs

- **The resource budget is full**: a due task waits and starts as soon as there is room. Tasks without a schedule go first, then the one that became due earliest. Waiting is strictly in that order, so a big cell is never overtaken by small ones behind it.
- **Themis was down**: occurrences that passed while it was off are **skipped**, not replayed. After the restart
  the next occurrence is computed from the current time.
- **A one-off task whose time has passed** runs as soon as it is Ready.

## Concurrency

How many cells run at the same time depends on the **resource budget** (CPUs and memory) under **Settings, Resources**, and
on the size of each cell. By default the budget fits two cells of the default size. A raised budget applies immediately.

## Reading the timeline

The **Schedule** tab of a project shows upcoming runs for the next 24 hours or 7 days, one row per task. Recurring
tasks are drawn in orange and one-off tasks in blue. The left edge is *now*, and the *Up next* list shows the nearest
runs. Very frequent schedules are drawn with thinner marks so they stay readable.

## When Themis restarts

If the server restarts while a task is running, the cell is removed and the attempt is closed as failed. A **recurring**
task then simply waits for its next occurrence. A **one-off** task is marked **Failed** rather than started again
automatically, because repeating an agent's work can repeat its side effects. Press **Run now** if you want it to retry.
