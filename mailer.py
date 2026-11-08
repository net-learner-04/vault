from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from datetime import datetime, timedelta
from config import SENDGRID_API_KEY, MAIL_FROM, MAIL_FROM_NAME
from dotenv import load_dotenv
import random
import string

verify_store = {}


def _generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))


def _build_html(title: str, message: str, code: str, expire_minutes: int):
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#07091a;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#07091a;padding:48px 16px;">
    <tr>
      <td align="center">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">

          <tr>
            <td align="center" style="padding-bottom:32px;">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:12px;padding:10px 14px;vertical-align:middle;">
                    <span style="font-size:18px;">&#9729;</span>
                  </td>
                  <td style="padding-left:10px;vertical-align:middle;">
                    <span style="color:#f0f0ff;font-size:1.15rem;font-weight:800;letter-spacing:-0.4px;">{MAIL_FROM_NAME}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:40px 36px;">

              <p style="margin:0 0 8px;color:#a5b4fc;font-size:0.75rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;">{title}</p>
              <h1 style="margin:0 0 16px;color:#f0f0ff;font-size:1.5rem;font-weight:800;letter-spacing:-0.5px;line-height:1.2;">{message}</h1>
              <p style="margin:0 0 28px;color:#a0a0c0;font-size:0.9rem;line-height:1.6;">Use the verification code below. It expires in <strong style="color:#f0f0ff;">{expire_minutes} minutes</strong>.</p>

              <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
                <tr>
                  <td align="center" style="background:rgba(99,102,241,0.12);border:1px solid rgba(99,102,241,0.25);border-radius:12px;padding:24px;">
                    <span style="color:#f0f0ff;font-size:2.5rem;font-weight:800;letter-spacing:0.35em;font-variant-numeric:tabular-nums;">{code}</span>
                  </td>
                </tr>
              </table>

              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(244,63,94,0.08);border:1px solid rgba(244,63,94,0.18);border-radius:10px;margin-bottom:8px;">
                <tr>
                  <td style="padding:12px 16px;color:#fb7185;font-size:0.82rem;line-height:1.5;">
                    If you did not request this code, you can safely ignore this email. Do not share this code with anyone.
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <tr>
            <td align="center" style="padding-top:28px;">
              <p style="margin:0;color:#555580;font-size:0.76rem;line-height:1.6;">
                This email was sent by {MAIL_FROM_NAME} &middot; Your private cloud storage<br/>
                &copy; {datetime.now().year} {MAIL_FROM_NAME}. All rights reserved.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _send_email(to: str, subject: str, html: str):
    message = Mail(
        from_email=(MAIL_FROM, MAIL_FROM_NAME),
        to_emails=to,
        subject=subject,
        html_content=html
    )
    sg = SendGridAPIClient(SENDGRID_API_KEY)
    sg.send(message)


def send_register_code(to: str):
    code = _generate_code()
    verify_store[to] = {
        "code": code,
        "expire": datetime.now() + timedelta(minutes=10),
        "type": "register"
    }
    html = _build_html(
        title="Email Verification",
        message="Verify your email address",
        code=code,
        expire_minutes=10
    )
    _send_email(to, f"[{MAIL_FROM_NAME}] Verify your email", html)


def send_reset_code(to: str):
    code = _generate_code()
    verify_store[to] = {
        "code": code,
        "expire": datetime.now() + timedelta(minutes=5),
        "type": "reset"
    }
    html = _build_html(
        title="Password Reset",
        message="Reset your password",
        code=code,
        expire_minutes=5
    )
    _send_email(to, f"[{MAIL_FROM_NAME}] Reset your password", html)


def verify_code(email: str, code: str, code_type: str = None):
    entry = verify_store.get(email)
    if not entry:
        return False
    if datetime.now() > entry["expire"]:
        del verify_store[email]
        return False
    if code_type and entry.get("type") != code_type:
        return False
    if entry["code"] != code:
        return False
    del verify_store[email]
    return True


def send_dormant_unlock_code(to: str):
    code = _generate_code()
    verify_store[to] = {
        "code": code,
        "expire": datetime.now() + timedelta(minutes=10),
        "type": "dormant"
    }
    html = _build_html(
        title="Account Reactivation",
        message="Reactivate your dormant account",
        code=code,
        expire_minutes=10
    )
    _send_email(to, f"[{MAIL_FROM_NAME}] Reactivate your account", html)
