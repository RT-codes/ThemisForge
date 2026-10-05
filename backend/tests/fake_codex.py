"""A stand-in for `codex login --device-auth`, driven by FAKE_CODEX_MODE (ok | wait | fail | hang)."""

import base64
import json
import os
import sys
import time
from pathlib import Path


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


mode = os.environ.get("FAKE_CODEX_MODE", "ok")
print("WARNING: proceeding, even though we could not create PATH aliases", flush=True)
print("\nWelcome to Codex [v0.0.0]\n", flush=True)
print("1. Open this link in your browser and sign in to your account", flush=True)
print("   https://auth.example.test/codex/device\n", flush=True)
print("2. Enter this one-time code (expires in 15 minutes)", flush=True)
print("   \x1b[94mABCD-12345\x1b[0m\n", flush=True)
print("Continue only if you started this login in Codex.", flush=True)

if mode == "wait":  # finish once the file named by FAKE_CODEX_GO exists (manual testing)
    while not Path(os.environ["FAKE_CODEX_GO"]).exists():
        time.sleep(0.2)
if mode == "hang":
    time.sleep(60)
elif mode == "fail":
    sys.exit(1)
else:
    time.sleep(0.2)
    auth = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": f"{b64({'alg': 'none'})}.{b64({'email': 'ada@example.test'})}.sig",
            "access_token": "ACCESS-TOKEN-SECRET",
            "refresh_token": "REFRESH-TOKEN-SECRET",
            "account_id": "acct-1",
        },
        "last_refresh": "2026-10-05T12:00:00Z",
    }
    Path(os.environ["CODEX_HOME"], "auth.json").write_text(json.dumps(auth))
