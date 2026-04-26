#!/usr/bin/env python3
"""Fetch bioRxiv preprints from the last 48h. Output slim JSON to stdout.

Stdlib only. Pre-filters to chromatin/cell biology adjacent categories so the
LLM downstream gets ~50-150 candidates instead of the full ~500/day flood.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "3d-genome-digest/1.0 (+https://github.com/YanXu2077/3d-genome-digest)"

# Bio-categories where 3D-genome / Micro-C / Hi-C papers tend to land.
KEEP_CATEGORIES = {
    "molecular biology",
    "genomics",
    "cell biology",
    "biophysics",
    "genetics",
    "systems biology",
    "bioinformatics",
    "developmental biology",
    "immunology",
    "cancer biology",
    "pathology",
    "synthetic biology",
}


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    date_from = yesterday.isoformat()
    date_to = today.isoformat()

    papers = []
    for cursor in range(0, 4000, 30):
        url = f"https://api.biorxiv.org/details/biorxiv/{date_from}/{date_to}/{cursor}"
        try:
            data = json.loads(http_get(url))
        except Exception as e:
            print(f"WARN cursor {cursor}: {e}", file=sys.stderr)
            break
        coll = data.get("collection", [])
        if not coll:
            break
        papers.extend(coll)

    keep_dates = {date_from, date_to}
    papers = [p for p in papers if p.get("date") in keep_dates]

    slim = []
    for p in papers:
        cat = (p.get("category") or "").lower()
        if cat and cat not in KEEP_CATEGORIES:
            continue
        doi = p.get("doi", "")
        slim.append({
            "title": p.get("title", ""),
            "authors": (p.get("authors", "") or "")[:400],
            "date": p.get("date", ""),
            "doi": doi,
            "url": f"https://www.biorxiv.org/content/{doi}v1" if doi else "",
            "category": p.get("category", ""),
            "abstract": p.get("abstract", ""),
        })

    out = {"window_utc": [date_from, date_to], "count": len(slim), "papers": slim}
    print(f"Fetched {len(papers)} in window, kept {len(slim)} after category filter", file=sys.stderr)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
