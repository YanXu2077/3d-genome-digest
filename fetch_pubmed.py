#!/usr/bin/env python3
"""Fetch PubMed articles from the last 48h matching chromatin/3D-genome
keywords. Output slim JSON to stdout, same shape as fetch_papers.py.

Uses NCBI E-utilities (no API key needed for low volume; 3 req/sec limit).
Stdlib only.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = "3d-genome-digest/1.0 (+https://github.com/YanXu2077/3d-genome-digest)"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Keyword filter at search time — keeps the result set manageable.
# Title/Abstract tagged ([TIAB]) so we don't get spurious matches in MeSH terms.
KEYWORDS = [
    '"chromatin"[TIAB]',
    '"Hi-C"[TIAB]',
    '"Micro-C"[TIAB]',
    '"cohesin"[TIAB]',
    '"CTCF"[TIAB]',
    '"loop extrusion"[TIAB]',
    '"TAD"[TIAB]',
    '"topologically associating"[TIAB]',
    '"3D genome"[TIAB]',
    '"chromosome conformation"[TIAB]',
    '"nucleosome"[TIAB]',
    '"single molecule"[TIAB]',
    '"single-molecule"[TIAB]',
    '"phase separation"[TIAB]',
    '"biomolecular condensate"[TIAB]',
    '"RNA polymerase II"[TIAB]',
    '"transcription factor"[TIAB] AND "dynamics"[TIAB]',
    '"enhancer-promoter"[TIAB]',
    '"polymer model"[TIAB] AND "chromatin"[TIAB]',
]


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def esearch(date_from, date_to, max_results=100):
    keyword_clause = "(" + " OR ".join(KEYWORDS) + ")"
    # PubMed expects YYYY/MM/DD format
    df = date_from.replace("-", "/")
    dt = date_to.replace("-", "/")
    date_clause = f'("{df}"[EDAT] : "{dt}"[EDAT])'
    term = f"{keyword_clause} AND {date_clause}"
    params = {
        "db": "pubmed",
        "term": term,
        "retmax": str(max_results),
        "retmode": "json",
        "sort": "date",
    }
    url = f"{BASE}/esearch.fcgi?" + urllib.parse.urlencode(params)
    data = json.loads(http_get(url))
    return data.get("esearchresult", {}).get("idlist", [])


def efetch(pmids):
    if not pmids:
        return ""
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    url = f"{BASE}/efetch.fcgi?" + urllib.parse.urlencode(params)
    return http_get(url).decode("utf-8", errors="replace")


def text(elem):
    if elem is None:
        return ""
    return "".join(elem.itertext()).strip()


def parse_articles(xml_text, date_from, date_to):
    if not xml_text.strip():
        return []
    root = ET.fromstring(xml_text)
    keep_dates = {date_from, date_to}
    out = []
    for art in root.iter("PubmedArticle"):
        try:
            cit = art.find(".//MedlineCitation/Article")
            if cit is None:
                continue
            title = text(cit.find("ArticleTitle"))
            abstract_parts = []
            for ab in cit.findall(".//Abstract/AbstractText"):
                label = ab.attrib.get("Label")
                t = text(ab)
                abstract_parts.append(f"{label}: {t}" if label else t)
            abstract = " ".join(abstract_parts).strip()

            authors = []
            for au in cit.findall(".//AuthorList/Author"):
                last = text(au.find("LastName"))
                init = text(au.find("Initials"))
                if last:
                    authors.append(f"{last} {init}".strip() if init else last)
            authors_str = "; ".join(authors)

            journal = text(cit.find(".//Journal/Title")) or text(cit.find(".//Journal/ISOAbbreviation"))

            # Use entrez date as the "date"
            edate = art.find(".//PubmedData/History/PubMedPubDate[@PubStatus='entrez']")
            if edate is not None:
                y = text(edate.find("Year"))
                m = text(edate.find("Month")).zfill(2)
                d = text(edate.find("Day")).zfill(2)
                date_str = f"{y}-{m}-{d}" if y else ""
            else:
                date_str = ""
            if date_str not in keep_dates:
                continue  # extra safety filter

            pmid = text(art.find(".//MedlineCitation/PMID"))
            doi = ""
            for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if aid.attrib.get("IdType") == "doi":
                    doi = text(aid)
                    break
            # Always use pubmed.ncbi direct URL — DOI redirect to publisher often 403s
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else (f"https://doi.org/{doi}" if doi else "")

            out.append({
                "title": title,
                "authors": authors_str[:400],
                "date": date_str,
                "doi": doi or f"pmid:{pmid}",
                "url": url,
                "category": journal,
                "abstract": abstract,
                "source": "PubMed",
            })
        except Exception as e:
            print(f"WARN parse error: {e}", file=sys.stderr)
    return out


def main():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    date_from = yesterday.isoformat()
    date_to = today.isoformat()

    pmids = esearch(date_from, date_to, max_results=100)
    print(f"PubMed esearch: {len(pmids)} hits in {date_from}..{date_to}", file=sys.stderr)
    if not pmids:
        json.dump({"window_utc": [date_from, date_to], "count": 0, "papers": []}, sys.stdout, ensure_ascii=False)
        return

    # Polite delay to respect NCBI rate limit
    time.sleep(0.4)
    xml_text = efetch(pmids)
    papers = parse_articles(xml_text, date_from, date_to)
    print(f"PubMed parsed: {len(papers)} papers retained after date filter", file=sys.stderr)

    json.dump({"window_utc": [date_from, date_to], "count": len(papers), "papers": papers},
              sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
