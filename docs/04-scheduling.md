---
title: Scheduling
group: Using ThemisForge
summary: Manual, one-off and recurring schedules, cron syntax, time zones and what happens when things are late.
---

# Scheduling

ThemisForge has one always-on scheduler. About every three seconds it looks for tasks that are **Ready** and **due**,
and starts a cell for each, up to the concurrency limit.

## Three kinds of schedule

| Kind | Behaviour |
| --- | --- |
| **Manual** | No schedule. Runs when the task is Ready and a cell is free, or when you press **Run now**. |
| **Once** | Runs a single time at a date and time you choose (shown in your local time). |
| **Recurring** | Runs on every occurrence of a cron expression, for as long as the task is Ready. |

## Cron in 30 seconds

A cron expression has five fields:

```text
┌───────── minute        (0-59)
│ ┌─────── hour          (0-23)
│ │ ┌───── day of month  (1-31)
│ │ │ ┌─── month         (1-12)
│ │ │ │ ┌─ day of week   (0-6, Sunday is 0)
│ │ │ │ │
* * * * *
```

| Expression | Meaning |
| --- | --- |
| `*/15 * * * *` | Every 15 minutes |
| `0 * * * *` | Every hour, on the hour |
| `0 9 * * *` | Every day at 09:00 |
| `0 9 * * 1-5` | Weekdays at 09:00 |
| `0 9 * * 1` | Every Monday at 09:00 |
| `30 18 1 * *` | The 1st of each month at 18:30 |

The task editor offers presets for the common ones and a field for your own expression. Expressions with six fields
(seconds) are rejected.

## Time zones

Recurring schedules are evaluated in the **time zone set on the Settings page**, not in UTC and not in your browser's
zone. "Every day at 09:00" therefore means 09:00 in that zone, including across daylight saving changes.

One-off times are picked in your browser's local time and stored as an exact moment.

## Pausing

A recurring task only runs while it is in **Ready**. Move it to **Inbox** to pause it and back to **Ready** to resume.
Resuming does not replay what was missed: the next occurrence is computed from the moment you resume.

## Late and missed runs

- **Cell slots are full**: a due task waits and starts as soon as a slot is free. Tasks without a schedule go first, then the one that became due earliest.
- **ThemisForge was down**: occurrences that passed while it was off are **skipped**, not replayed. After the restart
  the next occurrence is computed from the current time.
- **A one-off task whose time has passed** runs as soon as it is Ready.

## Concurrency

By default two cells run at the same time. Change it under **Settings, Cells**. A raised limit applies immediately.

## Reading the timeline

The **Schedule** tab of a project shows upcoming runs for the next 24 hours or 7 days, one row per task. Recurring
tasks are drawn in orange and one-off tasks in blue. The left edge is *now*, and the *Up next* list shows the nearest
runs. Very frequent schedules are drawn with thinner marks so they stay readable.

## When ThemisForge restarts

If the server restarts while a task is running, the cell is removed and the attempt is closed as failed. A **recurring**
task then simply waits for its next occurrence. A **one-off** task is marked **Failed** rather than started again
automatically, because repeating an agent's work can repeat its side effects. Press **Run now** if you want it to retry.
