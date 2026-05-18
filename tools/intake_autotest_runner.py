#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = "WA-Ladd"
REPO = "rigsr-relay"
BRANCH = "main"
VALID_TO = {"00", "01", "02", "03", "04", "05", "06", "99"}


def get_token():
    value = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not value:
        raise RuntimeError("Missing GITHUB_TOKEN or GH_TOKEN environment variable")
    return value


def github_api(method, path, body=None):
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/{path}"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {get_token()}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8")
        raise RuntimeError(f"GitHub API {method} {path} failed: {e.code} {detail}")


def make_relay_id(to):
    now = datetime.now(timezone.utc)
    year = now.year
    julian = now.timetuple().tm_yday
    sequence = now.strftime("%H%M%S")
    return f"99{to}{year}{julian:03d}{sequence}"


def create_file(path, content, message):
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    body = {
        "message": message,
        "content": encoded,
        "branch": BRANCH,
    }
    return github_api("PUT", f"contents/{path}", body)


def get_file(path):
    try:
        result = github_api("GET", f"contents/{path}?ref={BRANCH}")
    except RuntimeError as e:
        if " 404 " in str(e):
            return None
        raise

    encoded = result.get("content")
    if not encoded:
        return None

    return base64.b64decode(encoded).decode("utf-8")


def wait_for_file(path, timeout, interval):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if get_file(path) is not None:
            return True
        time.sleep(interval)

    return False


def wait_for_index(index_path, relay_filename, timeout, interval):
    deadline = time.time() + timeout

    while time.time() < deadline:
        content = get_file(index_path)

        if content is not None:
            data = json.loads(content)
            if relay_filename in data.get("pending", []):
                return True

        time.sleep(interval)

    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", required=True, help="Recipient id: 00, 01, 02, 03, 04, 05, 06, or 99")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()

    recipient = args.to.strip()

    if recipient not in VALID_TO:
        print(json.dumps({
            "result": "FAIL",
            "reason": "unsupported recipient",
            "recipient": recipient
        }, indent=2))
        return 2

    relay_id = make_relay_id(recipient)
    relay_filename = f"{relay_id}.json"

    relay = {
        "relay_id": relay_id,
        "type": "relay",
        "from": "99",
        "to": recipient,
        "task": f"Automated smoke test to {recipient}",
        "message": "Confirm receipt only. Do not route, implement, archive, or validate.",
        "context": None,
        "history": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }

    outbox_path = f"relay/outbox/{relay_filename}"
    inbox_path = f"relay/inbox/{relay_filename}"
    index_path = f"relay/index/{recipient}.json"
    undefined_index_path = "relay/index/undefined.json"

    create_file(
        outbox_path,
        json.dumps(relay, indent=2) + "\n",
        f"autotest relay {relay_id}"
    )

    inbox_ok = wait_for_file(inbox_path, args.timeout, args.interval)
    index_ok = wait_for_index(index_path, relay_filename, args.timeout, args.interval)
    undefined_index_absent = get_file(undefined_index_path) is None

    result = {
        "relay_id": relay_id,
        "recipient": recipient,
        "outbox_path": outbox_path,
        "inbox_path": inbox_path,
        "index_path": index_path,
        "inbox_ok": inbox_ok,
        "index_ok": index_ok,
        "undefined_index_absent": undefined_index_absent,
    }

    if inbox_ok and index_ok and undefined_index_absent:
        result["result"] = "PASS"
        print(json.dumps(result, indent=2))
        return 0

    result["result"] = "FAIL"
    print(json.dumps(result, indent=2))
    return 1


if __name__ == "__main__":
    sys.exit(main())
