#!/usr/bin/env python3
"""Read /tmp/chosen.json (written by claude-code-action), build HTML email,
and send via Resend API."""

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


def build_html(c, tier, commentary_zh):
    p = c
    title = escape(p.get("title", ""))
    authors = escape(short_authors(p.get("authors", "")))
    date = escape(p.get("date", ""))
    cat = escape(p.get("category", ""))
    url = p.get("url", "")
    abstract = escape(p.get("abstract", ""))
    note = escape(commentary_zh)
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;line-height:1.55;color:#222;">
  <h2 style="margin:0 0 6px 0;">{title}</h2>
  <p style="color:#666;margin:0 0 14px 0;font-size:14px;">{authors} &middot; {date} &middot; bioRxiv ({cat}) &middot; Tier {tier}</p>
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


def main():
    chosen_path = "/tmp/chosen.json"
    if not os.path.exists(chosen_path):
        # Claude failed to write the file — fall back to error report
        send("[3D Genome Daily] FAILED — chosen.json missing",
             "<p>Claude step did not produce /tmp/chosen.json. Check the workflow logs.</p>")
        sys.exit(1)

    with open(chosen_path, encoding="utf-8") as f:
        c = json.load(f)

    paper = c["chosen"]
    tier = c["tier"]
    commentary = c["commentary_zh"]
    subject_in = c.get("subject") or f"[3D Genome Daily] {paper.get('title','(untitled)')}"
    subject = truncate(subject_in, 100)
    html = build_html(paper, tier, commentary)
    resp = send(subject, html)
    print(f"Sent: {subject} [Tier {tier}] (id={resp.get('id')})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        # Try sending error notification — best effort
        try:
            send("[3D Genome Daily] FAILED — email step",
                 f"<pre>{escape(tb)}</pre>")
        except Exception:
            pass
        sys.exit(1)
