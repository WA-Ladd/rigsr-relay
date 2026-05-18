#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = "WA-Ladd"
REPO = "rigsr-relay"
BRANCH = "main"
MAILBOX_TO = {"00", "03", "05", "99"}
API_TO = {"01", "02", "04", "06"}
VALID_TO = MAILBOX_TO | API_TO


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
    return f"99{to}{now.year}{now.timetuple().tm_yday:03d}{now.strftime('%H%M%S')}"


def create_file(path, content, message):
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return github_api("PUT", f"contents/{path}", {
        "message": message,
        "content": encoded,
        "branch": BRANCH,
    })


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


def list_dir(path):
    try:
        result = github_api("GET", f"contents/{path}?ref={BRANCH}")
    except RuntimeError as e:
        if " 404 " in str(e):
            return []
        raise
    return result if isinstance(result, list) else []


def index_contains(index_path, relay_filename):
    content = get_file(index_path)
    if content is None:
        return False
    data = json.loads(content)
    return relay_filename in data.get("pending", [])


def find_response_to(original_relay_id, expected_from):
    candidates = []
    for item in list_dir("relay/inbox"):
        name = item.get("name", "")
        if not name.endswith(".json"):
            continue
        content = get_file(f"relay/inbox/{name}")
        if content is None:
            continue
        try:
            relay = json.loads(content)
        except json.JSONDecodeError:
            continue
        if relay.get("from") == expected_from and relay.get("to") == "99":
            if relay.get("history") == original_relay_id or original_relay_id in json.dumps(relay):
                candidates.append((name, relay))
    return candidates[-1] if candidates else None


def wait_mailbox(relay_filename, recipient, timeout, interval):
    inbox_path = f"relay/inbox/{relay_filename}"
    index_path = f"relay/index/{recipient}.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        inbox_ok = get_file(inbox_path) is not None
        index_ok = index_contains(index_path, relay_filename)
        if inbox_ok and index_ok:
            return True, inbox_ok, index_ok
        time.sleep(interval)
    return False, get_file(inbox_path) is not None, index_contains(index_path, relay_filename)


def wait_api(original_relay_id, recipient, timeout, interval):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = find_response_to(original_relay_id, recipient)
        if response:
            name, _relay = response
            if index_contains("relay/index/99.json", name):
                return True, name
        time.sleep(interval)
    response = find_response_to(original_relay_id, recipient)
    return False, response[0] if response else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", required=True, help="Recipient id: 00, 01, 02, 03, 04, 05, 06, or 99")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()

    recipient = args.to.strip()
    if recipient not in VALID_TO:
        print(json.dumps({"result": "FAIL", "reason": "unsupported recipient", "recipient": recipient}, indent=2))
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
    create_file(outbox_path, json.dumps(relay, indent=2) + "\n", f"autotest relay {relay_id}")

    undefined_index_absent = get_file("relay/index/undefined.json") is None
    result = {
        "relay_id": relay_id,
        "recipient": recipient,
        "mode": "api" if recipient in API_TO else "mailbox",
        "outbox_path": outbox_path,
        "undefined_index_absent": undefined_index_absent,
    }

    if recipient in MAILBOX_TO:
        ok, inbox_ok, index_ok = wait_mailbox(relay_filename, recipient, args.timeout, args.interval)
        result.update({
            "inbox_path": f"relay/inbox/{relay_filename}",
            "index_path": f"relay/index/{recipient}.json",
            "inbox_ok": inbox_ok,
            "index_ok": index_ok,
        })
        result["result"] = "PASS" if ok and undefined_index_absent else "FAIL"
    else:
        ok, response_file = wait_api(relay_id, recipient, args.timeout, args.interval)
        result.update({
            "expected_response_to": "99",
            "response_file": response_file,
            "user_index_path": "relay/index/99.json",
            "response_to_99_ok": ok,
        })
        result["result"] = "PASS" if ok and undefined_index_absent else "FAIL"

    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
