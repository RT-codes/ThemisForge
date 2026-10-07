"""A stand-in for the `docker` program, just enough for Codex's sign in: run, cp and rm (see test_codex_container.py).

`docker run --name N ... IMAGE codex login ...` runs fake_codex.py with CODEX_HOME pointing at a folder of its own, kept
as the "container" until `docker rm -f N`. Every call is appended to $FAKE_DOCKER_STATE/calls.log.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

state = Path(os.environ["FAKE_DOCKER_STATE"])
args = sys.argv[1:]
with (state / "calls.log").open("a") as log:
    log.write(" ".join(args) + "\n")

if os.environ.get("FAKE_DOCKER_MODE") == "daemon-down" and args[0] == "run":
    print("docker: Cannot connect to the Docker daemon. Is the docker daemon running?", flush=True)
    sys.exit(125)

if args[0] == "run":
    name = args[args.index("--name") + 1]
    home = state / name
    home.mkdir()
    env = {**os.environ, "CODEX_HOME": str(home)}
    sys.exit(
        subprocess.run(
            [sys.executable, str(Path(__file__).parent / "fake_codex.py")], env=env, check=False
        ).returncode
    )
elif args[0] == "cp":
    source, dest = args[1], args[2]
    name, _, inside = source.partition(":")
    file = state / name / Path(inside).name
    if not file.is_file():
        print(f"Error: No such container:path: {source}", file=sys.stderr)
        sys.exit(1)
    shutil.copy(file, dest)
elif args[0] == "rm":
    shutil.rmtree(state / args[-1], ignore_errors=True)
    (state / "removed.txt").open("a").write(args[-1] + "\n")
