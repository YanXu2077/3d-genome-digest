#!/usr/bin/env python3
"""Send a failure notification email when the digest workflow fails."""

import json
import os
import sys
import urllib.request
from html import escape

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "yanxu2077@gmail.com")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")
UA = "3d-genome-digest/1.0"

SERVER = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "")
RUN_ATTEMPT = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
RUN_URL = f"{SERVER}/{REPO}/actions/runs/{RUN_ID}/attempts/{RUN_ATTEMPT}" if RUN_ID else SERVER

html = f"""<div style="font-family:-apple-system,sans-serif;max-width:680px;line-height:1.55;color:#222;">
  <h2 style="margin:0 0 6px 0;">⚠️ Digest run failed</h2>
  <p style="color:#666;margin:0 0 14px 0;font-size:14px;">attempt {escape(RUN_ATTEMPT)} of run {escape(RUN_ID)}</p>
  <p>这次 cron 没发出 digest 邮件。如果是第 1 次尝试，<b>retry workflow 会自动再跑一次</b>。如果你又收到一封一样的邮件，说明 retry 也失败了，需要看 log。</p>
  <p><a href="{escape(RUN_URL)}">点这里看 GitHub Actions 详细日志</a></p>
  <p style="color:#999;font-size:13px;">常见原因：bioRxiv API 5xx / Claude rate limit / 网络抖动 / 代码 bug</p>
</div>"""

payload = json.dumps({
    "from": FROM_EMAIL,
    "to": TO_EMAIL,
    "subject": f"[3D Genome Daily] 🚨 run failed (attempt {RUN_ATTEMPT})",
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
    print(f"Failure notice sent: {body}")
