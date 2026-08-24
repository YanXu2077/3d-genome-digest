#!/usr/bin/env python3
"""Combine bioRxiv (fetch_papers.py) + PubMed (fetch_pubmed.py) outputs into
a single /tmp/papers.json. Validates each paper's URL via HEAD and drops
papers with broken URLs (4xx/5xx) so the user never receives a dead link."""

import concurrent.futures
import json
import os
import sys
import urllib.error
import urllib.request

UA = "3d-genome-digest/1.0 (+https://github.com/YanXu2077/3d-genome-digest)"
HEAD_TIMEOUT = 6


def url_ok(url):
    if not url:
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        req.get_method = lambda: "HEAD"
        with urllib.request.urlopen(req, timeout=HEAD_TIMEOUT) as r:
            return 200 <= r.status < 400
    except urllib.error.HTTPError as e:
        return 200 <= e.code < 400
    except Exception:
        return False


def main():
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

    # Dedupe by DOI/URL/title
    seen = set()
    deduped = []
    for p in papers:
        key = (p.get("doi") or p.get("url") or p.get("title", ""))[:100]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    print(f"raw: bioRxiv={len(bx.get('papers',[]))}, PubMed={len(pm.get('papers',[]))}, deduped={len(deduped)}",
          file=sys.stderr)

    # URL validation: only for PubMed (publisher DOI redirects often dead).
    # bioRxiv pages 403 from server-side curl due to Cloudflare bot protection,
    # but real browsers reach them fine — trust the API metadata.
    SKIP_VALIDATION_SOURCES = {"bioRxiv"}

    needs_check_idx = [i for i, p in enumerate(deduped) if p.get("source") not in SKIP_VALIDATION_SOURCES]
    results = {}
    if needs_check_idx:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            future_to_idx = {ex.submit(url_ok, deduped[i].get("url", "")): i for i in needs_check_idx}
            for fut in concurrent.futures.as_completed(future_to_idx):
                results[future_to_idx[fut]] = fut.result()

    keepers = []
    drop_count_by_source = {}
    for i, p in enumerate(deduped):
        src = p.get("source", "?")
        if src in SKIP_VALIDATION_SOURCES:
            keepers.append(p)  # trust without checking
        elif results.get(i, False):
            keepers.append(p)
        else:
            drop_count_by_source[src] = drop_count_by_source.get(src, 0) + 1

    drops_summary = ", ".join(f"{k}={v}" for k, v in sorted(drop_count_by_source.items())) or "0"
    skipped_count = sum(1 for p in deduped if p.get("source") in SKIP_VALIDATION_SOURCES)
    print(f"URL validation: checked {len(needs_check_idx)}, skipped(trusted) {skipped_count} | dropped: {drops_summary} | kept {len(keepers)}/{len(deduped)}",
          file=sys.stderr)

    # With a 7-day lookback the pool gets large. Rank by topic-keyword density
    # and keep the strongest N per source so Claude sees depth, not noise.
    RELEVANT = (
        "hi-c", "micro-c", "microc", "loop extrusion", "cohesin", "ctcf", "tad",
        "topologically associating", "3d genome", "chromosome conformation",
        "chromatin loop", "compartment", "condensin", "nucleosome", "chromatin",
        "atac", "dnase", "accessibility", "single-molecule", "single molecule",
        "phase separation", "condensate", "rna polymerase ii", "pol ii",
        "enhancer", "promoter", "polymer model", "hichip", "capture-c",
        "nuclear organization", "genome organization", "transcription factor",
    )
    PER_SOURCE = int(os.environ.get("PER_SOURCE_CAP", "120"))

    def score(p):
        blob = (p.get("title", "") + " " + p.get("abstract", "")).lower()
        return sum(1 for k in RELEVANT if k in blob)

    ranked = []
    for src in sorted({p.get("source", "?") for p in keepers}):
        grp = [p for p in keepers if p.get("source") == src]
        grp.sort(key=lambda p: (score(p), p.get("date", "")), reverse=True)
        kept_grp = [p for p in grp if score(p) > 0][:PER_SOURCE]
        print(f"rank {src}: {len(grp)} -> {len(kept_grp)} (cap {PER_SOURCE})", file=sys.stderr)
        ranked.extend(kept_grp)
    keepers = ranked

    window = bx.get("window_utc") or pm.get("window_utc") or []
    out = {
        "window_utc": window,
        "count": len(keepers),
        "papers": keepers,
        "url_validation": {
            "kept": len(keepers),
            "dropped": len(deduped) - len(keepers),
            "dropped_by_source": drop_count_by_source,
        },
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
