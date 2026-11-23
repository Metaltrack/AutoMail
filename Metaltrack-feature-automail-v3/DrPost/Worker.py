from contextlib import contextmanager
from email.message import EmailMessage
from smtplib import SMTP, SMTPRecipientsRefused

from logger import logger, log_level

log = logger()


class DrMail:
    """Sends mail through an SMTP server (Gmail by default).

    `session()` opens one SMTP connection for a batch and closes it afterwards,
    so no connection is left idle (Gmail drops idle ones) and no connection is
    shared between threads.

    In dry-run mode nothing is sent. Addresses ending in "@fail.test" fail on
    purpose, so retries and partial failures can be shown in a demo.
    """

    def __init__(self, sender_mail, app_password, host="smtp.gmail.com", port=587,
                 sender_name="Dr. Post", dry_run=False):
        self.sender_mail = sender_mail
        self.app_password = app_password
        self.host = host
        self.port = port
        self.sender_name = sender_name
        self.dry_run = dry_run

        if dry_run:
            log.log(log_level.WARNING, "Worker.py", "DRY RUN mode: mail is logged, not sent.")
        elif not sender_mail or not app_password:
            raise ValueError("SENDER_EMAIL and SENDER_APP_PASSWORD must be set (see .env.example).")

    def build(self, to_addr, sub, body, html=False, reply_to=None, attachments=()):
        msg = EmailMessage()
        # Gmail rewrites any other "From" to the logged-in account anyway, and
        # letting callers choose it invites spoofing.
        msg["From"] = f"{self.sender_name} <{self.sender_mail or 'dry-run@localhost'}>"
        msg["To"] = to_addr
        msg["Subject"] = sub
        if reply_to:
            msg["Reply-To"] = reply_to
        if html:
            msg.set_content("This message contains HTML. Please view it in an HTML-capable mail client.")
            msg.add_alternative(body, subtype="html")
        else:
            msg.set_content(body)
        for att in attachments:
            maintype, _, subtype = (att["content_type"] or "application/octet-stream").partition("/")
            msg.add_attachment(att["data"], maintype=maintype, subtype=subtype or "octet-stream",
                               filename=att["filename"])
        return msg

    @contextmanager
    def session(self):
        """Yields a send(msg) function backed by one SMTP connection."""
        if self.dry_run:
            def fake_send(msg):
                if str(msg["To"]).lower().endswith("@fail.test"):
                    raise SMTPRecipientsRefused({msg["To"]: (550, b"dry-run test failure")})
                log.log(log_level.INFO, "Worker.py", f"[dry run] '{msg['Subject']}' -> {msg['To']}")
            yield fake_send
            return

        smtp = SMTP(self.host, self.port, timeout=30)  # the constructor already connects
        try:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(self.sender_mail, self.app_password)

            def send(msg):
                smtp.send_message(msg)
                log.log(log_level.INFO, "Worker.py", f"Sent '{msg['Subject']}' -> {msg['To']}")
            yield send
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
