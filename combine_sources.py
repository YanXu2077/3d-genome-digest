#!/usr/bin/env python3
"""Combine bioRxiv (fetch_papers.py) + PubMed (fetch_pubmed.py) outputs into
a single /tmp/papers.json. Validates each paper's URL via HEAD and drops
papers with broken URLs (4xx/5xx) so the user never receives a dead link."""

import concurrent.futures
import json
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

    # Validate URLs in parallel
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        future_to_idx = {ex.submit(url_ok, p.get("url", "")): i for i, p in enumerate(deduped)}
        for fut in concurrent.futures.as_completed(future_to_idx):
            results[future_to_idx[fut]] = fut.result()

    keepers = []
    drop_count_by_source = {}
    for i, p in enumerate(deduped):
        if results.get(i, False):
            keepers.append(p)
        else:
            src = p.get("source", "?")
            drop_count_by_source[src] = drop_count_by_source.get(src, 0) + 1

    drops_summary = ", ".join(f"{k}={v}" for k, v in sorted(drop_count_by_source.items())) or "0"
    print(f"URL validation: kept {len(keepers)}/{len(deduped)} | dropped: {drops_summary}",
          file=sys.stderr)

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
