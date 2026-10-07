# Security

Themis runs AI agents on your machine, so security reports are taken seriously. Thank you for taking the time.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Report it privately instead:

1. Go to the repository's **Security** tab and choose **Report a vulnerability** (GitHub's private reporting), or
2. open it directly: <https://github.com/RT-codes/ThemisForge/security/advisories/new>

Please include what you found, the steps to reproduce it, the version (`GET /api/version`, or `./themis doctor`), and the
effect you think it has. A short description is enough to start; we will ask if we need more.

What to expect, from a small project with one maintainer: a reply within about 5 days, a fix or a plan for one as soon as
we can, and credit in the release notes if you want it. There is no bug bounty.

## Supported versions

While Themis is below 1.0, only the **latest release** gets security fixes. Upgrade with `themis upgrade` when a new
version is announced; the app tells administrators when one is available.

## What counts

Reports we are especially glad to get:

- a way for a cell (an agent's container) to reach the host, other projects, other users' files or the Docker socket,
- reading or writing outside a folder through the Files page or any other path handling,
- an account taking over another's session, project or stored keys, or skipping the invite-only sign-up,
- stored keys, Codex logins or the secret key showing up in a log, a result, an API answer or a file,
- anything that lets someone without administrator rights do what only an administrator may.

## How Themis is meant to be used

Knowing the intended model helps judge what is a bug:

- **A cell is the safety fence.** Agents run inside a throwaway Docker container and only see the folders you give them,
  where they can do anything the folder's access allows. An agent changing files in a folder you mounted read-write is
  expected, not a vulnerability. Only share folders you are comfortable with them changing.
- **Docker access is powerful.** Whoever can use Docker on the machine can effectively act as root there. Themis only
  talks to Docker from the server process.
- **Administrators are trusted.** An administrator can add keys, approve host folders and change settings; reports that need
  administrator rights to begin with are usually out of scope.
- **Expose it with HTTPS.** By default Themis only answers on the machine itself. If you open it to a network, put a
  reverse proxy with HTTPS in front and set `THEMIS_COOKIE_SECURE=true`. See the
  [operations guide](docs/08-operations.md).
- **Keys are encrypted, not hidden from agents you give them to.** An agent that is given a key can use it, and a
  determined agent can reveal it. Only give keys to agents you trust with them.
