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
    # Widen the lookback so a quiet 48h does not force a bad pick. sent_history
    # dedupes, so older-but-unsent papers surface instead of Tier 4 filler.
    window_days = int(os.environ.get("WINDOW_DAYS", "7"))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=window_days - 1)
    date_from = start.isoformat()
    date_to = today.isoformat()

    papers = []
    for cursor in range(0, 12000, 30):
        url = f"https://api.biorxiv.org/details/biorxiv/{date_from}/{date_to}/{cursor}"
        # Retry on transient errors (bioRxiv API occasionally 5xx / bad JSON)
        attempts, last_err = 3, None
        for i in range(attempts):
            try:
                data = json.loads(http_get(url))
                last_err = None
                break
            except Exception as e:
                last_err = e
                print(f"WARN cursor {cursor} attempt {i+1}: {e}", file=sys.stderr)
                if i < attempts - 1:
                    import time as _t; _t.sleep(2 ** i)
        if last_err is not None:
            print(f"bioRxiv fetch giving up at cursor {cursor}", file=sys.stderr)
            break
        coll = data.get("collection", [])
        if not coll:
            break
        papers.extend(coll)

    keep_dates = {(start + timedelta(days=i)).isoformat() for i in range(window_days)}
    papers = [p for p in papers if p.get("date") in keep_dates]

    slim = []
    skipped_revisions = 0
    for p in papers:
        # v1 only — a revision landing in the window is not new work.
        if str(p.get("version", "1")).strip() != "1":
            skipped_revisions += 1
            continue
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

    # Relevance prescreen: a 7-day window would otherwise hand Claude ~3000
    # papers. Keep only those whose title/abstract touches the reader's topics,
    # newest first, capped. This removes Tier 4 filler at the source.
    RELEVANT = (
        "hi-c", "micro-c", "microc", "loop extrusion", "cohesin", "ctcf", "tad",
        "topologically associating", "3d genome", "chromosome conformation",
        "chromatin loop", "compartment", "condensin", "nucleosome", "chromatin",
        "atac", "dnase", "accessibility", "single-molecule", "single molecule",
        "phase separation", "condensate", "rna polymerase ii", "pol ii",
        "enhancer", "promoter", "polymer model", "hichip", "capture-c",
        "nuclear organization", "genome organization", "transcription factor",
    )
    MAX_POOL = int(os.environ.get("MAX_POOL", "220"))

    def hits(p):
        blob = (p.get("title", "") + " " + p.get("abstract", "")).lower()
        return sum(1 for k in RELEVANT if k in blob)

    scored = [(hits(p), p) for p in slim]
    matched = [(n, p) for n, p in scored if n > 0]
    matched.sort(key=lambda t: (t[1].get("date", ""), t[0]), reverse=True)
    dropped_irrelevant = len(slim) - len(matched)
    slim = [p for _, p in matched[:MAX_POOL]]
    print(f"prescreen: dropped {dropped_irrelevant} with no topic keyword, "
          f"capped to {len(slim)} (max {MAX_POOL})", file=sys.stderr)

    out = {"window_utc": [date_from, date_to], "count": len(slim), "papers": slim}
    print(f"Fetched {len(papers)} in window, dropped {skipped_revisions} non-v1, "
          f"kept {len(slim)} after category filter", file=sys.stderr)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
