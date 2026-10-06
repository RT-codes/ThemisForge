---
title: Troubleshooting
group: Running it
summary: Common problems and how to fix them.
---

# Troubleshooting

Start with `./themis doctor`. It checks the most common causes and tells you what to fix.

## Docker says "permission denied"

The user that runs Themis is not allowed to talk to Docker. The installer adds it to the `docker` group and the
service picks the group up automatically. If you changed this by hand:

```bash
sudo usermod -aG docker $USER
./themis service restart
```

Your *shell* only sees a new group after you log out and in again. The service does not need that.

## Docker is not reachable

The daemon is stopped, or the Docker host in Settings is wrong. Try `sudo systemctl start docker`, or clear the
**Docker host** field to use the local engine, then press **Test**.

## A Ready task does not start

Check, in this order:

1. **Is it due?** A task with a schedule waits for its time. The card shows when.
2. **Are the cells full?** The header shows *n/m cells*. Raise the limit under Settings, or wait.
3. **Is the scheduler on?** The header says *Scheduler on*. If it says off, check `./themis service logs`.
4. **Is Docker healthy?** A task that fails the moment it starts usually has the reason in its **History** log.

## An attempt fails straight away

Open the task, go to **History** and read the log. The usual causes:

- the **image** cannot be pulled (typo, no network, private registry),
- Docker is unreachable,
- the image has no `sh`.

## A recurring task runs at the wrong hour

Recurring schedules use the **time zone in Settings**, not your browser's. Check it there.

## A recurring task did not run while the server was off

By design. Missed occurrences are skipped, and the next one is computed after the restart. See
[Scheduling](/docs/scheduling).

## A one-off task shows Failed after a restart

It was running when the server stopped. Themis does not repeat it automatically because that could repeat side
effects. Press **Run now** to try again.

## I lost an invite link

Links are shown only once. Create a new invite for the same email address in **Access**: it replaces the old one.

## I forgot my password

There is no password reset yet. It is on the [roadmap](/docs/roadmap).

## Stored keys stopped working

`THEMIS_SECRET_KEY` changed. Keys are encrypted with a key derived from it, so they must be added again.

## The disk is filling up

Two places grow over time: Docker images and the data folder.

```bash
docker image prune          # remove unused images
du -sh data/projects/*      # see which project uses the space
```

## Start over

To wipe an installation completely (this deletes all data):

```bash
./themis service stop
rm backend/themisforge.db* ; rm -rf data
./themis service start
```
