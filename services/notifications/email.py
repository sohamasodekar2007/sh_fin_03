"""
Shared email transport — extracted from apps/api/routers/auth.py's OTP
sender (the only place that sent real email before this) so the Supervisor
approval email (Phase 5) reuses the exact same Brevo -> Resend -> SMTP
delivery chain rather than re-implementing it.

send_email_sync() only knows how to move a subject+html to an address —
callers (auth.py's OTP mail, this module's own approval-email builder) own
their own HTML content.
"""

from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any


def send_email_sync(to_email: str, subject: str, html: str, settings: Any) -> bool:
    """Best-effort send: Brevo HTTP API -> Resend HTTP API -> raw SMTP.
    Returns True the moment any transport reports success, False if every
    configured transport failed (or none were configured) — the caller
    already printed/logged the content, so nothing is lost in dev."""
    sender_email = settings.smtp_from
    if not sender_email or "@smtp-brevo.com" in sender_email or "@" not in sender_email:
        sender_email = "teamalpha817@gmail.com"

    if settings.brevo_api_key:
        try:
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=json.dumps(
                    {
                        "sender": {"email": sender_email, "name": "CloudCare"},
                        "to": [{"email": to_email}],
                        "subject": subject,
                        "htmlContent": html,
                    }
                ).encode("utf-8"),
                headers={
                    "api-key": settings.brevo_api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req) as response:
                response.read()
                return True
        except urllib.error.HTTPError as e:
            print(f"[email] Brevo API error: {e.code} - {e.read().decode('utf-8')}")
        except Exception as e:
            print(f"[email] Brevo API error: {e}")

    if settings.resend_api_key:
        try:
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps(
                    {
                        "from": "CloudCare <onboarding@resend.dev>",
                        "to": to_email,
                        "subject": subject,
                        "html": html,
                    }
                ).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req) as response:
                response.read()
                return True
        except urllib.error.HTTPError as e:
            print(f"[email] Resend API error: {e.code} - {e.read().decode('utf-8')}")
        except Exception as e:
            print(f"[email] Resend API error: {e}")

    if settings.smtp_username and settings.smtp_password:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.smtp_from or settings.smtp_username
            msg["To"] = to_email
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(msg["From"], [to_email], msg.as_string())
            return True
        except Exception as e:
            print(f"[email] SMTP error: {e}")

    return False


def build_approval_email_html(context: dict[str, Any]) -> str:
    """context: resource_name, action_plain_english, savings_monthly,
    confidence_score, risk_score, rationale, approve_url, reject_url."""
    return f"""
    <html>
      <body style="font-family: sans-serif; padding: 20px; color: #10222E; background-color: #F7FAF9;">
        <div style="max-width: 520px; margin: 0 auto; background: #FFFFFF; border: 1px solid #E4EBE8; border-radius: 8px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
          <h2 style="margin-top: 0; color: #2F6690;">CloudCare — Cost Optimization Awaiting Your Approval</h2>
          <p style="font-size: 14px;"><strong>Resource:</strong> {context['resource_name']}</p>
          <p style="font-size: 14px;"><strong>Proposed action:</strong> {context['action_plain_english']}</p>
          <div style="display: flex; gap: 12px; margin: 16px 0;">
            <div style="flex: 1; background: #E4EBE8; border-radius: 6px; padding: 12px; text-align: center;">
              <div style="font-size: 20px; font-weight: bold; color: #2F6690;">${context['savings_monthly']}/mo</div>
              <div style="font-size: 11px; color: #627785;">Estimated savings</div>
            </div>
            <div style="flex: 1; background: #E4EBE8; border-radius: 6px; padding: 12px; text-align: center;">
              <div style="font-size: 20px; font-weight: bold; color: #2F6690;">{context['confidence_score']:.0%}</div>
              <div style="font-size: 11px; color: #627785;">Confidence</div>
            </div>
            <div style="flex: 1; background: #E4EBE8; border-radius: 6px; padding: 12px; text-align: center;">
              <div style="font-size: 20px; font-weight: bold; color: #2F6690;">{context['risk_score']:.0%}</div>
              <div style="font-size: 11px; color: #627785;">Risk</div>
            </div>
          </div>
          <p style="font-size: 13px; color: #627785;">{context['rationale']}</p>
          <div style="margin: 24px 0; text-align: center;">
            <a href="{context['approve_url']}" style="display: inline-block; margin: 0 8px; padding: 12px 28px; background: #2F6690; color: #FFFFFF; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px;">Approve</a>
            <a href="{context['reject_url']}" style="display: inline-block; margin: 0 8px; padding: 12px 28px; background: #FFFFFF; color: #B3261E; border: 1.5px solid #B3261E; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px;">Reject</a>
          </div>
          <p style="font-size: 12px; color: #627785;">This link expires in 24 hours and can only be used once. If you're not signed in, you'll be asked to log in first — the click itself is what carries the authority to act.</p>
        </div>
      </body>
    </html>
    """


def send_approval_email_sync(to_email: str, context: dict[str, Any], settings: Any) -> bool:
    subject = f"CloudCare — Approve: {context['action_plain_english']} on {context['resource_name']}"
    html = build_approval_email_html(context)
    print(f"[Supervisor] Approval email to {to_email}: {subject}")
    return send_email_sync(to_email, subject, html, settings)


def build_completion_email_html(context: dict[str, Any]) -> str:
    """context: resource_arn, action_type, status, predicted_savings_monthly,
    rollback_link (Phase 6 — services/executor/actions.py)."""
    return f"""
    <html>
      <body style="font-family: sans-serif; padding: 20px; color: #10222E; background-color: #F7FAF9;">
        <div style="max-width: 520px; margin: 0 auto; background: #FFFFFF; border: 1px solid #E4EBE8; border-radius: 8px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
          <h2 style="margin-top: 0; color: #2F6690;">CloudCare — Action Completed</h2>
          <p style="font-size: 14px;"><strong>Resource:</strong> {context['resource_arn']}</p>
          <p style="font-size: 14px;"><strong>What changed:</strong> {context['action_type']} ({context['status']})</p>
          <div style="background: #E4EBE8; border-radius: 6px; padding: 12px; margin: 16px 0;">
            <div style="font-size: 20px; font-weight: bold; color: #2F6690;">${context['predicted_savings_monthly']}/mo</div>
            <div style="font-size: 11px; color: #627785;">Predicted savings — actual savings will be confirmed once the next billing cycle's FOCUS data lands</div>
          </div>
          <div style="margin: 24px 0; text-align: center;">
            <a href="{context['rollback_link']}" style="display: inline-block; padding: 12px 28px; background: #FFFFFF; color: #B3261E; border: 1.5px solid #B3261E; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px;">View / Roll back in dashboard</a>
          </div>
          <p style="font-size: 12px; color: #627785;">Rolling back requires signing in — this is a more sensitive action than approving, so it isn't a one-click email link.</p>
        </div>
      </body>
    </html>
    """


def send_completion_email_sync(to_email: str, context: dict[str, Any], settings: Any) -> bool:
    subject = f"CloudCare — Completed: {context['action_type']} on {context['resource_arn']}"
    html = build_completion_email_html(context)
    print(f"[Executor] Completion email to {to_email}: {subject}")
    return send_email_sync(to_email, subject, html, settings)
