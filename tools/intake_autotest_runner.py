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
MAILBOX_TO = ["00", "03", "05", "99"]
API_TO = ["01", "02", "04", "06"]
VALID_TO = set(MAILBOX_TO + API_TO)


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


def read_index_pending(path):
    content = get_file(path)
    if content is None:
        return []

    data = json.loads(content)
    return list(data.get("pending", []))


def index_contains(index_path, relay_filename):
    return relay_filename in read_index_pending(index_path)


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


def wait_api(previous_user_pending, timeout, interval):
    deadline = time.time() + timeout

    while time.time() < deadline:
        current = read_index_pending("relay/index/99.json")
        added = [name for name in current if name not in previous_user_pending]

        if added:
            newest = added[-1]
            if get_file(f"relay/inbox/{newest}") is not None:
                return True, newest

        time.sleep(interval)

    current = read_index_pending("relay/index/99.json")
    added = [name for name in current if name not in previous_user_pending]
    return False, added[-1] if added else None


def run_single(recipient, timeout, interval):
    previous_user_pending = read_index_pending("relay/index/99.json") if recipient in API_TO else []

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

    create_file(
        outbox_path,
        json.dumps(relay, indent=2) + "\n",
        f"autotest relay {relay_id}"
    )

    undefined_index_absent = get_file("relay/index/undefined.json") is None

    result = {
        "relay_id": relay_id,
        "recipient": recipient,
        "mode": "api" if recipient in API_TO else "mailbox",
        "undefined_index_absent": undefined_index_absent,
    }

    if recipient in MAILBOX_TO:
        ok, inbox_ok, index_ok = wait_mailbox(relay_filename, recipient, timeout, interval)

        result.update({
            "inbox_ok": inbox_ok,
            "index_ok": index_ok,
        })

        result["result"] = "PASS" if ok and undefined_index_absent else "FAIL"

    else:
        ok, response_file = wait_api(previous_user_pending, timeout, interval)

        result.update({
            "response_file": response_file,
            "response_to_99_ok": ok,
        })

        result["result"] = "PASS" if ok and undefined_index_absent else "FAIL"

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--to")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dead-letter", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--interval", type=int, default=3)
    args = parser.parse_args()

    if args.dead_letter:
        relay_id = make_relay_id("98")
        relay = {
            "relay_id": relay_id,
            "type": "relay",
            "from": "99",
            "to": "98",
            "task": "Dead-letter smoke test",
            "message": "This relay should dead-letter.",
            "context": None,
            "history": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }

        create_file(
            f"relay/outbox/{relay_id}.json",
            json.dumps(relay, indent=2) + "\n",
            f"dead-letter test {relay_id}"
        )

        time.sleep(10)

        undefined_exists = get_file("relay/index/undefined.json") is not None

        result = {
            "test": "dead-letter",
            "undefined_index_absent": not undefined_exists,
            "result": "PASS" if not undefined_exists else "FAIL"
        }

        print(json.dumps(result, indent=2))
        return 0 if result["result"] == "PASS" else 1

    if args.all:
        results = []

        for recipient in MAILBOX_TO + API_TO:
            results.append(run_single(recipient, args.timeout, args.interval))

        summary = {
            "result": "PASS" if all(r["result"] == "PASS" for r in results) else "FAIL",
            "results": results
        }

        print(json.dumps(summary, indent=2))
        return 0 if summary["result"] == "PASS" else 1

    if not args.to:
        print(json.dumps({"result": "FAIL", "reason": "missing --to or --all"}, indent=2))
        return 2

    recipient = args.to.strip()

    if recipient not in VALID_TO:
        print(json.dumps({"result": "FAIL", "reason": "unsupported recipient", "recipient": recipient}, indent=2))
        return 2

    result = run_single(recipient, args.timeout, args.interval)
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
