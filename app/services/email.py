"""
app/services/email.py
─────────────────────
Email delivery via Resend (https://resend.com).

Why Resend?
  ✓ Free tier: 3 000 emails / month, no credit card needed
  ✓ Single API call, no SMTP config
  ✓ Python SDK: `pip install resend`
  ✓ Easy to set up a verified sender domain (or use onboarding@resend.dev
    for the first domain while testing)

Setup:
  1. Sign up at https://resend.com
  2. Add RESEND_API_KEY to your .env
  3. Verify a sender domain (or use the Resend sandbox for testing)
"""

import logging
import resend
from app.config import settings

logger = logging.getLogger(__name__)

# ── Markdown → simple HTML ─────────────────────────────────────────────────────

def _md_to_html(md: str) -> str:
    """
    Very light Markdown → HTML conversion (no extra deps).
    For production you could swap this with `markdown` or `mistune`.
    """
    import re

    lines    = md.split("\n")
    html_lines: list[str] = []

    for line in lines:
        # Headers
        if line.startswith("### "):
            line = f"<h3>{line[4:]}</h3>"
        elif line.startswith("## "):
            line = f"<h2>{line[3:]}</h2>"
        elif line.startswith("# "):
            line = f"<h1>{line[2:]}</h1>"
        # Bullet
        elif line.startswith("• ") or line.startswith("- "):
            line = f"<li>{line[2:]}</li>"
        # Bold
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        # Links [text](url)
        line = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', line)
        # Empty line → paragraph break
        if not line.strip():
            line = "<br/>"
        html_lines.append(line)

    body = "\n".join(html_lines)
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 680px; margin: 0 auto; padding: 24px; color: #1a1a1a; }}
  h1   {{ color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
  h2   {{ color: #1e293b; margin-top: 28px; }}
  h3   {{ color: #334155; }}
  li   {{ margin-bottom: 12px; line-height: 1.6; }}
  a    {{ color: #2563eb; }}
  br   {{ margin-bottom: 8px; }}
</style>
</head>
<body>
{body}
</body>
</html>
""".strip()


# ── Public function ────────────────────────────────────────────────────────────

def send_digest_email(
    digest_markdown: str,
    recipient: str | None = None,
    sender: str | None = None,
) -> None:
    """
    Send the daily digest email via Resend.

    Args:
        digest_markdown: The digest content in Markdown format.
        recipient:       Override the configured recipient email.
        sender:          Override the configured sender email.

    Raises:
        RuntimeError: If the Resend API key is not configured.
        Exception:    Propagates any Resend API error.
    """
    api_key = settings.resend_api_key
    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY is not set. "
            "Sign up at https://resend.com and add the key to your .env file."
        )

    resend.api_key = api_key

    to_addr   = recipient or settings.digest_recipient_email
    from_addr = sender   or settings.digest_sender_email

    if not to_addr:
        raise RuntimeError("DIGEST_RECIPIENT_EMAIL is not configured.")

    html_body = _md_to_html(digest_markdown)

    params = {
        "from":    from_addr,
        "to":      [to_addr],
        "subject": "🤖 Your Daily AI News Digest",
        "html":    html_body,
        "text":    digest_markdown,   # plain-text fallback
    }

    logger.info("Sending digest email via Resend → %s", to_addr)
    response = resend.Emails.send(params)
    logger.info("Resend response: %s", response)