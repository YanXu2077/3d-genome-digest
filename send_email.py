#!/usr/bin/env python3
"""Send one digest email. Called twice per workflow:
  python send_email.py preprint   → reads /tmp/preprint_*.txt
  python send_email.py journal    → reads /tmp/journal_*.txt

If the corresponding _doi.txt is missing or empty, exits cleanly (no candidate
for that source today; skip silently)."""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html import escape

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "yanxu2077@gmail.com")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")
UA = "3d-genome-digest/1.0 (+https://github.com/YanXu2077/3d-genome-digest)"

KIND = sys.argv[1] if len(sys.argv) > 1 else "preprint"
assert KIND in ("preprint", "journal"), f"Unknown kind {KIND!r}"

LABEL = "Preprint" if KIND == "preprint" else "Journal"


def short_authors(s):
    parts = [a.strip() for a in re.split(r";|,", s or "") if a.strip()]
    if len(parts) <= 5:
        return ", ".join(parts)
    return ", ".join(parts[:5]) + ", et al."


def truncate(s, limit):
    return s if len(s) <= limit else s[: limit - 1] + "…"


def build_html(p, tier, commentary_zh):
    title_raw = p.get("title", "")
    title = escape(title_raw)
    authors = escape(short_authors(p.get("authors", "")))
    date = escape(p.get("date", ""))
    cat = escape(p.get("category", ""))
    src = escape(p.get("source", "bioRxiv"))
    url = p.get("url", "")
    doi = p.get("doi", "")
    abstract = escape(p.get("abstract", ""))
    note = escape(commentary_zh)
    src_label = f"{src} ({cat})" if cat else src

    scholar_url = "https://scholar.google.com/scholar?q=" + urllib.parse.quote(title_raw)
    doi_url = f"https://doi.org/{doi}" if doi and not doi.startswith("pmid:") else ""
    links = [f'<a href="{url}">{src} link</a>']
    if doi_url and doi_url != url:
        links.append(f'<a href="{escape(doi_url)}">doi.org</a>')
    links.append(f'<a href="{escape(scholar_url)}">Google Scholar</a>')
    links_html = " &middot; ".join(links)

    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;line-height:1.55;color:#222;">
  <h2 style="margin:0 0 6px 0;">{title}</h2>
  <p style="color:#666;margin:0 0 14px 0;font-size:14px;">{authors} &middot; {date} &middot; {src_label} &middot; Tier {tier}</p>
  <p style="font-size:14px;">{links_html}</p>
  <h3 style="margin-top:22px;">中文点评</h3>
  <p>{note}</p>
  <h3 style="margin-top:22px;">Abstract</h3>
  <p>{abstract}</p>
</div>"""


def send(subject, html):
    payload = json.dumps({
        "from": FROM_EMAIL, "to": TO_EMAIL, "subject": subject, "html": html,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload,
        headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                 "Content-Type": "application/json",
                 "User-Agent": UA, "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", errors="replace")
        print(f"Resend response: {body}")
        return json.loads(body)


def read_text(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def main():
    doi = read_text(f"/tmp/{KIND}_doi.txt")
    tier_raw = read_text(f"/tmp/{KIND}_tier.txt", "4")
    commentary = read_text(f"/tmp/{KIND}_commentary.txt")

    if not doi:
        print(f"[{KIND}] no DOI written by Claude — no candidate for this source today, skipping")
        return  # graceful skip

    with open("/tmp/papers.json", encoding="utf-8") as f:
        pool = json.load(f)
    papers = pool.get("papers", [])

    paper = next((p for p in papers if p.get("doi", "") == doi), None)
    if paper is None:
        # Claude wrote a DOI but it doesn't match the pool — fallback
        print(f"[{KIND}] DOI {doi!r} not found in pool, skipping", file=sys.stderr)
        return

    try:
        tier = int(tier_raw)
    except ValueError:
        tier = 4

    title = paper.get("title", "(untitled)")
    subject = truncate(f"[{LABEL}] {title}", 100)
    html = build_html(paper, tier, commentary)
    resp = send(subject, html)
    print(f"Sent: {subject} [Tier {tier}] (id={resp.get('id')})")

    # Append to /tmp/sent_this_run.json so update_history step picks both
    sent_path = "/tmp/sent_this_run.json"
    sent = []
    if os.path.exists(sent_path):
        with open(sent_path, encoding="utf-8") as f:
            try:
                sent = json.load(f)
            except Exception:
                sent = []
    sent.append({"chosen": paper, "tier": tier, "commentary_zh": commentary, "kind": KIND})
    with open(sent_path, "w", encoding="utf-8") as f:
        json.dump(sent, f, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            send(f"[3D Genome Daily] FAILED — {KIND} email crashed",
                 f"<pre>{escape(tb)}</pre>")
        except Exception:
            pass
        sys.exit(1)
