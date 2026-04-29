#!/usr/bin/env python3
"""Combine bioRxiv (fetch_papers.py) + PubMed (fetch_pubmed.py) outputs into a
single /tmp/papers.json. Adds a `source` field so downstream knows where each
paper came from."""

import json
import sys

with open("/tmp/biorxiv.json", encoding="utf-8") as f:
    bx = json.load(f)
with open("/tmp/pubmed.json", encoding="utf-8") as f:
    pm = json.load(f)

papers = []
for p in bx.get("papers", []):
    p.setdefault("source", "bioRxiv")
    papers.append(p)
for p in pm.get("papers", []):
    p.setdefault("source", "PubMed")
    papers.append(p)

# Deduplicate by DOI (a paper may appear in both)
seen = set()
deduped = []
for p in papers:
    key = (p.get("doi") or p.get("url") or p.get("title", ""))[:100]
    if key in seen:
        continue
    seen.add(key)
    deduped.append(p)

window = bx.get("window_utc") or pm.get("window_utc") or []
out = {"window_utc": window, "count": len(deduped), "papers": deduped}
print(f"combined: bioRxiv={len(bx.get('papers',[]))}, PubMed={len(pm.get('papers',[]))}, deduped={len(deduped)}",
      file=sys.stderr)
json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
