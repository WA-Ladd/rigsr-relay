#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VALID_TO = {"00", "01", "02", "03", "04", "05", "06", "99"}


def sh(cmd):
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout)
    return r.stdout.strip()


def root():
    return Path(sh(["git", "rev-parse", "--show-toplevel"]))


def relay_id(to):
    now = datetime.now(timezone.utc)
    return f"99{to}{now.year}{now.timetuple().tm_yday:03d}{now.strftime('%H%M%S')}"


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def pull():
    sh(["git", "pull", "--ff-only"])


def push_main():
    sh(["git", "push", "origin", "HEAD:main"])


def wait_for_file(path, timeout, interval):
    end = time.time() + timeout
    while time.time() < end:
        pull()
        if path.exists():
            return True
        time.sleep(interval)
    return False


def wait_for_index(path, filename, timeout, interval):
    end = time.time() + timeout
    while time.time() < end:
        pull()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if filename in data.get("pending", []):
                return True
        time.sleep(interval)
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True)
    p.add_argument("--timeout", type=int, default=90)
    p.add_argument("--interval", type=int, default=5)
    a = p.parse_args()

    if a.to not in VALID_TO:
        print(f"FAIL unsupported recipient {a.to}")
        return 2

    repo = root()
    rid = relay_id(a.to)
    fn = rid + ".json"

    relay = {
        "relay_id": rid,
        "type": "relay",
        "from": "99",
        "to": a.to,
        "task": f"Automated smoke test to {a.to}",
        "message": "Confirm receipt only. Do not route, implement, archive, or validate.",
        "context": None,
        "history": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending"
    }

    outbox = repo / "relay" / "outbox" / fn
    inbox = repo / "relay" / "inbox" / fn
    index = repo / "relay" / "index" / f"{a.to}.json"
    undefined = repo / "relay" / "index" / "undefined.json"

    write(outbox, relay)
    sh(["git", "add", str(outbox)])
    sh(["git", "commit", "-m", f"autotest relay {rid}"])
    push_main()

    inbox_ok = wait_for_file(inbox, a.timeout, a.interval)
    index_ok = wait_for_index(index, fn, a.timeout, a.interval)
    pull()
    undefined_ok = not undefined.exists()

    result = {
        "relay_id": rid,
        "inbox_ok": inbox_ok,
        "index_ok": index_ok,
        "undefined_index_absent": undefined_ok
    }

    print(json.dumps(result, indent=2))
    if inbox_ok and index_ok and undefined_ok:
        print("PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
