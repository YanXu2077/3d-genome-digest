#!/usr/bin/env python3
"""Read Claude's plain-text outputs (no JSON escape issues), look up paper
metadata from papers.json, build HTML, send via Resend.

Inputs (written by claude-code-action):
  /tmp/chosen_doi.txt        — DOI of the picked paper
  /tmp/chosen_tier.txt       — "1" / "2" / "3" / "4"
  /tmp/chosen_commentary.txt — Chinese commentary (raw text)

Inputs (written by fetch_papers.py):
  /tmp/papers.json — the candidate pool (always valid JSON)

Output: writes /tmp/chosen.json for downstream history step.
"""

import json
import os
import re
import sys
import urllib.request
from html import escape

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "yanxu2077@gmail.com")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")
UA = "3d-genome-digest/1.0 (+https://github.com/YanXu2077/3d-genome-digest)"


def short_authors(s):
    parts = [a.strip() for a in re.split(r";|,", s or "") if a.strip()]
    if len(parts) <= 5:
        return ", ".join(parts)
    return ", ".join(parts[:5]) + ", et al."


def truncate(s, limit):
    return s if len(s) <= limit else s[: limit - 1] + "…"


def build_html(p, tier, commentary_zh):
    title = escape(p.get("title", ""))
    authors = escape(short_authors(p.get("authors", "")))
    date = escape(p.get("date", ""))
    cat = escape(p.get("category", ""))
    src = escape(p.get("source", "bioRxiv"))
    url = p.get("url", "")
    abstract = escape(p.get("abstract", ""))
    note = escape(commentary_zh)
    src_label = f"{src} ({cat})" if cat else src
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;line-height:1.55;color:#222;">
  <h2 style="margin:0 0 6px 0;">{title}</h2>
  <p style="color:#666;margin:0 0 14px 0;font-size:14px;">{authors} &middot; {date} &middot; {src_label} &middot; Tier {tier}</p>
  <p><a href="{url}">{url}</a></p>
  <h3 style="margin-top:22px;">中文点评</h3>
  <p>{note}</p>
  <h3 style="margin-top:22px;">Abstract</h3>
  <p>{abstract}</p>
</div>"""


def send(subject, html):
    payload = json.dumps({
        "from": FROM_EMAIL,
        "to": TO_EMAIL,
        "subject": subject,
        "html": html,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": UA,
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", errors="replace")
        print(f"Resend response: {body}")
        return json.loads(body)


def read_text(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def fallback_pick(papers):
    """If Claude failed to produce outputs, pick the most recent paper as
    a token reading so the user still gets *something*."""
    if not papers:
        return None
    papers_sorted = sorted(papers, key=lambda p: p.get("date", ""), reverse=True)
    return papers_sorted[0]


def main():
    with open("/tmp/papers.json", encoding="utf-8") as f:
        pool = json.load(f)
    papers = pool.get("papers", [])

    doi = read_text("/tmp/chosen_doi.txt", "")
    tier_raw = read_text("/tmp/chosen_tier.txt", "4")
    commentary = read_text("/tmp/chosen_commentary.txt", "")

    try:
        tier = int(tier_raw)
    except ValueError:
        tier = 4

    paper = None
    if doi:
        paper = next((p for p in papers if p.get("doi", "") == doi), None)

    fallback_used = False
    if paper is None:
        paper = fallback_pick(papers)
        fallback_used = True
        if not commentary:
            commentary = "（Claude 步骤失败，自动 fallback 到 48h 内最新一篇 preprint。请检查 Actions 日志。）"

    if paper is None:
        # Truly nothing — send error notice
        send("[3D Genome Daily] FAILED — fetch + Claude 都失败了",
             "<p>没有候选 paper（fetch_papers 可能挂了），也没有 Claude 输出。检查 Actions 日志。</p>")
        sys.exit(1)

    title = paper.get("title", "(untitled)")
    subject = truncate(f"[3D Genome Daily] {title}", 100)
    if fallback_used:
        subject = "[3D Genome Daily fallback] " + truncate(title, 80)

    html = build_html(paper, tier, commentary)
    resp = send(subject, html)
    print(f"Sent: {subject} [Tier {tier}]{' (fallback)' if fallback_used else ''} (id={resp.get('id')})")

    # Write /tmp/chosen.json for downstream history step
    with open("/tmp/chosen.json", "w", encoding="utf-8") as f:
        json.dump({"chosen": paper, "tier": tier, "commentary_zh": commentary,
                   "fallback": fallback_used}, f, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            send("[3D Genome Daily] FAILED — email step crashed",
                 f"<pre>{escape(tb)}</pre>")
        except Exception:
            pass
        sys.exit(1)
