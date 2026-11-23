"""The emails AutoMail sends about accounts: verify your address, reset your password.

They go out straight away through the same SMTP account as everything else
(not through the user-facing queue, so they never wait behind a big mailing).
Failures are logged; the user can always ask for the mail again.
"""
import html as html_lib

from logger import logger, log_level

log = logger()


def _render(doctor, to, subject, intro, button, link, outro):
    """A plain-text mail with an HTML alternative (button), as one message."""
    text = f"{intro}\n\n{button}: {link}\n\n{outro}\n\n-- {doctor.sender_name}"
    page = (
        '<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;color:#1b2a4a">'
        f'<p style="font-size:15px;line-height:1.5">{html_lib.escape(intro)}</p>'
        f'<p><a href="{html_lib.escape(link)}" style="display:inline-block;background:#f2b705;color:#1b2a4a;'
        f'padding:12px 22px;border-radius:6px;text-decoration:none;font-weight:bold">{html_lib.escape(button)}</a></p>'
        f'<p style="font-size:12px;color:#667">Button not working? Paste this into your browser:<br>'
        f'{html_lib.escape(link)}</p>'
        f'<p style="font-size:13px;color:#667">{html_lib.escape(outro)}</p></div>'
    )
    msg = doctor.build(to, subject, text)
    msg.add_alternative(page, subtype="html")
    return msg


def deliver(doctor, to, subject, intro, button, link, outro):
    """Sends one account email. Never raises (it runs after the HTTP response)."""
    try:
        if doctor.dry_run:
            log.log(log_level.WARNING, "account_mail.py", f"[dry run] '{subject}' for {to}\n    {button}: {link}")
            return
        with doctor.session() as send:
            send(_render(doctor, to, subject, intro, button, link, outro))
    except Exception as err:
        log.log(log_level.ERROR, "account_mail.py", f"Could not send '{subject}' to {to}: {err}")


def verification(doctor, to, username, link):
    deliver(doctor, to, "Confirm your email for AutoMail",
            f"Hi {username}, confirm this email address to finish creating your AutoMail account.",
            "Confirm my email", link,
            "The link works for 24 hours. If you didn't sign up, you can ignore this message.")


def password_reset(doctor, to, username, link):
    deliver(doctor, to, "Reset your AutoMail password",
            f"Hi {username}, we got a request to reset your AutoMail password.",
            "Choose a new password", link,
            "The link works for 1 hour and only once. If you didn't ask for this, ignore this message: your password is unchanged.")
