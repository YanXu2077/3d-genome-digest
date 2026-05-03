#!/usr/bin/env python3
"""Append all just-sent papers (from /tmp/sent_this_run.json, written by
send_email.py) to sent_history.json. Trim to last MAX_ENTRIES."""

import json
import os
import sys
from datetime import datetime, timezone

SENT_PATH = "/tmp/sent_this_run.json"
HIST_PATH = "sent_history.json"
MAX_ENTRIES = 80

if not os.path.exists(SENT_PATH):
    print("no /tmp/sent_this_run.json — nothing was sent, skipping", file=sys.stderr)
    sys.exit(0)

with open(SENT_PATH, encoding="utf-8") as f:
    sent = json.load(f)

if not sent:
    print("empty sent list — nothing to log", file=sys.stderr)
    sys.exit(0)

if os.path.exists(HIST_PATH):
    with open(HIST_PATH, encoding="utf-8") as f:
        hist = json.load(f)
else:
    hist = []

now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
for s in sent:
    paper = s.get("chosen", {})
    hist.append({
        "doi": paper.get("doi", ""),
        "title": paper.get("title", "")[:200],
        "sent_at": now_iso,
        "tier": s.get("tier"),
        "kind": s.get("kind"),
    })

hist = hist[-MAX_ENTRIES:]
with open(HIST_PATH, "w", encoding="utf-8") as f:
    json.dump(hist, f, indent=2, ensure_ascii=False)

print(f"history now has {len(hist)} entries; appended {len(sent)} this run")
