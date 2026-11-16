#!/usr/bin/env python3
"""Publish the next queued carousel to Instagram.

Runs from GitHub Actions. Uses only the Python standard library.

How it decides what to do:
  * Posting slots are 8:00 am and 8:00 pm US Eastern. A slot stays open for
    three hours, so a late-starting job still posts.
  * Each slot is used at most once (recorded in state.json).
  * The next carousel is the first folder, in name order, inside queue/.
  * After a successful post the folder moves to posted/ with a result.json.
  * An empty queue, or a file named PAUSED in the repository root, means
    nothing is posted.

Flags:
  --dry-run   Validate and print what would be posted. Calls nothing, changes nothing.
  --force     Ignore the slot check and act on the next carousel now.
  --check     Validate every folder in queue/ and exit.

The access token is read from the IG_ACCESS_TOKEN environment variable and is
never printed.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue"
POSTED = ROOT / "posted"
STATE = ROOT / "state.json"
PAUSED = ROOT / "PAUSED"

EASTERN = ZoneInfo("America/New_York")
SLOT_HOURS = (8, 20)       # 8:00 am and 8:00 pm US Eastern
SLOT_WINDOW_HOURS = 3      # how long after a slot time a late job may still post

MIN_SLIDES = 2
MAX_SLIDES = 10
MAX_CAPTION_CHARS = 2200
MAX_HASHTAGS = 30

GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v26.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"


class PublishError(Exception):
    pass


# ---------------------------------------------------------------- slots

def due_slot(now_utc):
    """Return the id of the slot that is open right now, or None."""
    now_et = now_utc.astimezone(EASTERN)
    for hour in SLOT_HOURS:
        start = now_et.replace(hour=hour, minute=0, second=0, microsecond=0)
        if start <= now_et < start + timedelta(hours=SLOT_WINDOW_HOURS):
            return start.strftime("%Y-%m-%dT%H")
    return None


def read_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def write_state(state):
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- queue

def queued_folders():
    if not QUEUE.is_dir():
        return []
    return sorted(
        p for p in QUEUE.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    )


def load_carousel(folder):
    """Validate a carousel folder. Returns (slides, caption) or raises."""
    slides = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg")
    )
    others = [
        p.name for p in folder.iterdir()
        if p.is_file() and p not in slides and p.name != "caption.txt"
    ]
    problems = []
    if not MIN_SLIDES <= len(slides) <= MAX_SLIDES:
        problems.append(
            f"has {len(slides)} JPEG slides; needs {MIN_SLIDES} to {MAX_SLIDES}"
        )
    for p in slides:
        with p.open("rb") as fh:
            if fh.read(3) != b"\xff\xd8\xff":
                problems.append(f"{p.name} is not a real JPEG file")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", p.name):
            problems.append(f"{p.name}: use only letters, digits, dot, dash, underscore")
    if others:
        problems.append("unexpected files: " + ", ".join(sorted(others)))
    if not re.fullmatch(r"[A-Za-z0-9._-]+", folder.name):
        problems.append("folder name: use only letters, digits, dot, dash, underscore")

    caption_file = folder / "caption.txt"
    caption = ""
    if not caption_file.is_file():
        problems.append("caption.txt is missing")
    else:
        caption = caption_file.read_text(encoding="utf-8").strip()
        if not caption:
            problems.append("caption.txt is empty")
        if len(caption) > MAX_CAPTION_CHARS:
            problems.append(
                f"caption is {len(caption)} characters; the limit is {MAX_CAPTION_CHARS}"
            )
        hashtags = re.findall(r"(?<!\w)#\w+", caption)
        if len(hashtags) > MAX_HASHTAGS:
            problems.append(
                f"caption has {len(hashtags)} hashtags; the limit is {MAX_HASHTAGS}"
            )
    if problems:
        raise PublishError(f"queue/{folder.name}: " + "; ".join(problems))
    return slides, caption


def image_url(folder, slide):
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise PublishError("GITHUB_REPOSITORY is not set")
    # A commit id gives an address that cannot change under Instagram's feet.
    ref = os.environ.get("GITHUB_SHA") or os.environ.get("GITHUB_REF_NAME") or "main"
    path = urllib.parse.quote(f"queue/{folder.name}/{slide.name}")
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"


# ---------------------------------------------------------------- Instagram API

def _scrub(text, token):
    return text.replace(token, "[token hidden]") if token else text


def api(method, path, token, params=None):
    params = dict(params or {})
    url = f"{GRAPH}/{path}"
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if method == "GET":
        if params:
            url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            detail = json.loads(body).get("error", {})
            message = (
                f"{detail.get('message', body)} "
                f"(code {detail.get('code')}, subcode {detail.get('error_subcode')})"
            )
        except (ValueError, AttributeError):
            message = body
        raise PublishError(
            f"Instagram refused {method} {path}: " + _scrub(message, token)
        ) from None
    except urllib.error.URLError as err:
        raise PublishError(f"Could not reach Instagram: {err.reason}") from None


def wait_until_ready(container_id, token, tries=20, pause=5):
    for _ in range(tries):
        status = api("GET", container_id, token, {"fields": "status_code"})
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram could not process the carousel ({code})")
        time.sleep(pause)
    raise PublishError("Instagram took too long to process the carousel")


def publish(folder, slides, caption, token, user_id):
    children = []
    for slide in slides:
        made = api("POST", f"{user_id}/media", token, {
            "image_url": image_url(folder, slide),
            "is_carousel_item": "true",
        })
        children.append(made["id"])
        print(f"  uploaded {slide.name}")
    carousel = api("POST", f"{user_id}/media", token, {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
    })
    wait_until_ready(carousel["id"], token)
    published = api("POST", f"{user_id}/media_publish", token, {
        "creation_id": carousel["id"],
    })
    media_id = published["id"]
    permalink = None
    try:
        permalink = api("GET", media_id, token, {"fields": "permalink"}).get("permalink")
    except PublishError:
        pass  # the post is live; the link is only a convenience
    return media_id, permalink


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    folders = queued_folders()

    if args.check:
        failed = False
        for folder in folders:
            try:
                slides, _ = load_carousel(folder)
                print(f"ok    queue/{folder.name} ({len(slides)} slides)")
            except PublishError as err:
                failed = True
                print(f"FAIL  {err}")
        print(f"{len(folders)} carousel(s) in the queue.")
        return 1 if failed else 0

    if PAUSED.exists():
        print("Paused: a PAUSED file is in the repository. Nothing posted.")
        return 0

    now = datetime.now(timezone.utc)
    slot = due_slot(now)
    state = read_state()

    if not args.force:
        if slot is None:
            print("No posting slot is open right now. Nothing posted.")
            return 0
        if state.get("last_slot") == slot:
            print(f"Slot {slot} (US Eastern) was already used. Nothing posted.")
            return 0

    if not folders:
        print("The queue is empty. Nothing posted.")
        return 0

    folder = folders[0]
    slides, caption = load_carousel(folder)
    print(f"Next carousel: queue/{folder.name} ({len(slides)} slides)")

    if args.dry_run:
        print("Dry run. This is what would be posted:")
        for slide in slides:
            print(f"  slide   {slide.name}")
        print("  caption " + caption.replace("\n", "\n          "))
        print(f"{len(folders) - 1} more carousel(s) wait behind it.")
        return 0

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("IG_USER_ID", "").strip()
    if not token:
        raise PublishError("The IG_ACCESS_TOKEN secret is missing or empty")
    if not user_id.isdigit():
        raise PublishError("IG_USER_ID is missing or is not a number")

    media_id, permalink = publish(folder, slides, caption, token, user_id)

    POSTED.mkdir(exist_ok=True)
    destination = POSTED / folder.name
    shutil.move(str(folder), str(destination))
    (destination / "result.json").write_text(json.dumps({
        "media_id": media_id,
        "permalink": permalink,
        "posted_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "slot_us_eastern": slot,
        "forced": bool(args.force),
    }, indent=2) + "\n", encoding="utf-8")
    if slot is not None:
        state["last_slot"] = slot
    state["last_posted"] = folder.name
    write_state(state)

    print(f"Posted {folder.name}" + (f": {permalink}" if permalink else ""))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PublishError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
