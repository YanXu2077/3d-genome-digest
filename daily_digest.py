#!/usr/bin/env python3
"""
3D Genome Daily Digest
Pulls bioRxiv preprints from the last 48h, picks the most relevant one for a
researcher in the 3D genome / Micro-C / loop extrusion / single-molecule
space, and emails a Chinese summary + English abstract via Resend.

Designed to run on GitHub Actions cron. Stdlib only.

Env vars:
  RESEND_API_KEY  required
  TO_EMAIL        recipient (default yanxu2077@gmail.com)
  FROM_EMAIL      sender (default onboarding@resend.dev)
"""

import json
import os
import re
import sys
import traceback
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from html import escape

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "yanxu2077@gmail.com")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")
UA = "3d-genome-digest/1.0 (+https://github.com/YanXu2077/3d-genome-digest)"

TIER1 = [
    r"\bhi-?c\b", r"\bmicro-?c\b", r"\b3d genome\b",
    r"\bloop extrusion\b", r"\bcohesin\b", r"\bctcf\b",
    r"\bchromosome conformation\b", r"\b(tad|tads)\b",
    r"\btopologically associating\b",
    r"\bchromatin (architecture|organization|conformation|structure|looping|loops|loop|domain|domains|interaction|interactions|folding|topology)\b",
    r"\bgenome (folding|architecture|organization|topology)\b",
    r"\bcondensin\b", r"\benhancer-promoter\b",
    r"\bnuclear organization\b", r"\bnucleosome resolution\b",
]

TIER2 = [
    r"\bsingle[ -]molecule\b", r"\bsingle[ -]particle tracking\b", r"\bspt\b",
    r"\blive[ -]cell imaging\b", r"\bsuper[ -]resolution\b", r"\bsmlm\b",
    r"\blattice light sheet\b",
    r"\btranscription factor (binding|dynamics|kinetics|residence)\b",
    r"\bchromatin (dynamics|accessibility|state|landscape)\b",
    r"\bphase separation\b", r"\bcondensate(s)?\b", r"\bbiomolecular condensate\b",
    r"\brna pol(ymerase)? ii\b", r"\btranscriptional bursting\b",
    r"\bpolymer (physics|model|simulation)\b", r"\bsmc\b",
    r"\bnuclear (body|bodies|speckle|compartment)\b",
    r"\benhancer\b", r"\bpromoter\b",
    r"\bgene regulation\b", r"\bcis-?regulatory\b",
]

TIER3_CATEGORIES = {
    "molecular biology", "genomics", "cell biology", "biophysics",
    "genetics", "systems biology", "bioinformatics",
}


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_biorxiv(date_from, date_to):
    papers = []
    for cursor in range(0, 4000, 30):
        url = f"https://api.biorxiv.org/details/biorxiv/{date_from}/{date_to}/{cursor}"
        data = json.loads(http_get(url))
        coll = data.get("collection", [])
        if not coll:
            break
        papers.extend(coll)
    keep = {date_from, date_to}
    return [p for p in papers if p.get("date") in keep]


def fetch_arxiv(date_from, date_to):
    """Pull recent q-bio submissions via arXiv API."""
    cats = ["q-bio.GN", "q-bio.QM", "q-bio.BM", "q-bio.MN"]
    out = []
    for cat in cats:
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending&max_results=40"
        )
        try:
            xml = http_get(url).decode("utf-8", errors="replace")
        except Exception as e:
            print(f"arxiv {cat} fetch failed: {e}", file=sys.stderr)
            continue
        for entry in re.finditer(r"<entry>(.*?)</entry>", xml, re.DOTALL):
            block = entry.group(1)
            def grab(tag):
                m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.DOTALL)
                return m.group(1).strip() if m else ""
            title = re.sub(r"\s+", " ", grab("title"))
            summary = re.sub(r"\s+", " ", grab("summary"))
            published = grab("published")[:10]
            arxiv_id_match = re.search(r"<id>http[^<]*?abs/([^<]+)</id>", block)
            arxiv_id = arxiv_id_match.group(1) if arxiv_id_match else ""
            authors = [m.group(1).strip() for m in re.finditer(r"<author>\s*<name>([^<]+)</name>", block)]
            if published in (date_from, date_to):
                out.append({
                    "title": title,
                    "abstract": summary,
                    "authors": "; ".join(authors),
                    "date": published,
                    "doi": "",
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                    "category": cat,
                    "source": "arXiv",
                })
    return out


def normalize_biorxiv(p):
    doi = p.get("doi", "")
    return {
        "title": p.get("title", ""),
        "abstract": p.get("abstract", ""),
        "authors": p.get("authors", ""),
        "date": p.get("date", ""),
        "doi": doi,
        "url": f"https://www.biorxiv.org/content/{doi}v1" if doi else "",
        "category": p.get("category", ""),
        "source": "bioRxiv",
    }


def match_count(paper, patterns):
    text = (paper["title"] + ". " + paper["abstract"]).lower()
    return sum(1 for pat in patterns if re.search(pat, text))


def pick(papers, today_str):
    t1, t2, t3 = [], [], []
    for p in papers:
        c1 = match_count(p, TIER1)
        c2 = match_count(p, TIER2)
        if c1 > 0:
            t1.append((c1, p))
        elif c2 > 0:
            t2.append((c2, p))
        elif p["category"].lower() in TIER3_CATEGORIES:
            t3.append(p)

    print(f"Tier 1: {len(t1)} | Tier 2: {len(t2)} | Tier 3: {len(t3)}")

    if t1:
        t1.sort(key=lambda x: (x[1]["date"] == today_str, x[0]), reverse=True)
        return t1[0][1], 1
    if t2:
        t2.sort(key=lambda x: (x[1]["date"] == today_str, x[0]), reverse=True)
        return t2[0][1], 2
    if t3:
        t3.sort(key=lambda p: p["date"], reverse=True)
        return t3[0], 3
    if papers:
        papers.sort(key=lambda p: p["date"], reverse=True)
        return papers[0], 4
    return None, None


def short_authors(s):
    parts = [a.strip() for a in re.split(r";|,", s) if a.strip()]
    if len(parts) <= 5:
        return ", ".join(parts)
    return ", ".join(parts[:5]) + ", et al."


def commentary(paper, tier):
    """Heuristic stub. The real commentary should be generated by a richer
    model — but for now we punt to the human and just describe what was found.

    Replace this function later with an LLM call if desired.
    """
    title = paper["title"]
    abstract_l = paper["abstract"].lower()
    bits = []

    if tier == 1:
        signals = []
        for label, pat in [
            ("Micro-C", r"\bmicro-?c\b"),
            ("Hi-C", r"\bhi-?c\b"),
            ("loop extrusion", r"\bloop extrusion\b"),
            ("CTCF", r"\bctcf\b"),
            ("cohesin", r"\bcohesin\b"),
            ("TAD", r"\b(tad|tads|topologically associating)\b"),
            ("compartment", r"\bcompartment(s|alization)?\b"),
            ("enhancer-promoter loop", r"\benhancer-promoter\b"),
            ("polymer model", r"\bpolymer (physics|model|simulation)\b"),
        ]:
            if re.search(pat, abstract_l):
                signals.append(label)
        if signals:
            bits.append(f"这篇直接命中 {'、'.join(signals)} 等关键词，属于 3D genome / 染色质组织的核心方向。")
        bits.append("从你关心的 Micro-C / loop extrusion 视角看，可重点对照它的实验体系和分辨率与你目前数据的差异。")
    elif tier == 2:
        bits.append("不是严格的 3D genome 主题，但落在染色质动力学 / 单分子 / 凝聚体 / 转录因子 / 聚合物物理这一圈相邻方向。")
        bits.append("可以扫一眼方法和结论，看是否能反过来解释或补充 contact map 上观察到的现象。")
    else:
        bits.append("近 48 小时内 bioRxiv + arXiv q-bio 没有 3D genome / 染色质组织相关的新 preprint。")
        bits.append(f"这篇是从当日 {paper['category']} 领域里挑出来的最新 preprint，作为今天的占位读物。")

    return " ".join(bits)


def build_html(paper, tier):
    title = escape(paper["title"])
    authors = escape(short_authors(paper["authors"]))
    date = escape(paper["date"])
    source = escape(paper["source"])
    if paper.get("category"):
        source += f" ({escape(paper['category'])})"
    url = paper["url"]
    abstract = escape(paper["abstract"])
    note = escape(commentary(paper, tier))
    return f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 680px; line-height: 1.55; color: #222;">
  <h2 style="margin: 0 0 6px 0;">{title}</h2>
  <p style="color: #666; margin: 0 0 14px 0; font-size: 14px;">{authors} &middot; {date} &middot; {source} &middot; Tier {tier}</p>
  <p><a href="{url}">{url}</a></p>
  <h3 style="margin-top: 22px;">中文点评</h3>
  <p>{note}</p>
  <h3 style="margin-top: 22px;">Abstract</h3>
  <p>{abstract}</p>
</div>"""


def truncate_subject(s, limit=80):
    return s if len(s) <= limit else s[: limit - 1] + "…"


def send_email(subject, html):
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


def send_error_report(err_text):
    html = (
        '<div style="font-family: -apple-system, sans-serif; color: #222;">'
        "<h3>Digest run failed</h3>"
        "<pre style=\"background:#f4f4f4; padding:10px; overflow:auto;\">"
        f"{escape(err_text)}"
        "</pre>"
        "</div>"
    )
    try:
        send_email("[3D Genome Daily] FAILED — see body", html)
    except Exception as e:
        print(f"failed to send error email: {e}", file=sys.stderr)


def main():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    date_from = yesterday.isoformat()
    date_to = today.isoformat()
    print(f"Window: {date_from} to {date_to} UTC")

    papers = []
    try:
        bx = fetch_biorxiv(date_from, date_to)
        print(f"bioRxiv: {len(bx)}")
        papers.extend(normalize_biorxiv(p) for p in bx)
    except Exception as e:
        print(f"bioRxiv fetch failed: {e}", file=sys.stderr)

    try:
        ax = fetch_arxiv(date_from, date_to)
        print(f"arXiv: {len(ax)}")
        papers.extend(ax)
    except Exception as e:
        print(f"arXiv fetch failed: {e}", file=sys.stderr)

    if not papers:
        raise RuntimeError("No papers fetched from any source in the 48h window")

    chosen, tier = pick(papers, date_to)
    if chosen is None:
        raise RuntimeError("Pick returned None despite non-empty paper list")

    print(f"Chosen [Tier {tier}]: {chosen['title']}")
    subject = truncate_subject(f"[3D Genome Daily] {chosen['title']}")
    html = build_html(chosen, tier)
    resp = send_email(subject, html)
    print(f"Sent: {chosen['title']} (id={resp.get('id')}, tier={tier})")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        send_error_report(tb)
        sys.exit(1)
