#!/usr/bin/env python3
"""Append the just-sent paper's DOI to sent_history.json. Trim to last 60."""

import json
import os
import sys
from datetime import datetime, timezone

CHOSEN_PATH = "/tmp/chosen.json"
HIST_PATH = "sent_history.json"
MAX_ENTRIES = 60

if not os.path.exists(CHOSEN_PATH):
    print("no /tmp/chosen.json — skipping history update", file=sys.stderr)
    sys.exit(0)

with open(CHOSEN_PATH, encoding="utf-8") as f:
    c = json.load(f)

paper = c.get("chosen", {})
doi = paper.get("doi") or paper.get("url") or paper.get("title")
if not doi:
    print("no doi/url/title to record — skipping", file=sys.stderr)
    sys.exit(0)

if os.path.exists(HIST_PATH):
    with open(HIST_PATH, encoding="utf-8") as f:
        hist = json.load(f)
else:
    hist = []

hist.append({
    "doi": paper.get("doi", ""),
    "title": paper.get("title", "")[:200],
    "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "tier": c.get("tier"),
})
hist = hist[-MAX_ENTRIES:]

with open(HIST_PATH, "w", encoding="utf-8") as f:
    json.dump(hist, f, indent=2, ensure_ascii=False)

print(f"history now has {len(hist)} entries; latest doi={paper.get('doi','?')[:60]}")
