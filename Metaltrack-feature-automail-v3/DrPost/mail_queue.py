"""Background sender: scheduling, recurring jobs, retries and rate limits.

Every send becomes a *job* (subject, body, recipients, when to send) with one
*message* row per recipient. A background thread wakes every couple of seconds:

1. Due scheduled jobs are "opened": a message row is created per recipient.
   A recurring job also books its next run (tomorrow / next week).
2. Pending messages are sent, oldest first, while the hourly and daily limits
   allow. A failed message is retried with growing waits (30 s, 2 min, 8 min)
   before it is marked failed.
3. A job whose messages are all finished is marked done / partial / failed.

Everything lives in SQLite, so scheduled mail survives a server restart.
"""
import html as html_lib
import json
import os
import re
import smtplib
import threading
from pathlib import Path

import db
from logger import logger, log_level

log = logger()

DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "450"))        # Gmail allows about 500 a day
PER_MINUTE_LIMIT = int(os.getenv("PER_MINUTE_LIMIT", "20"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
BATCH_SIZE = 25
TICK_SECONDS = float(os.getenv("QUEUE_TICK_SECONDS", "2"))
REPEAT_SECONDS = {"daily": 86400, "weekly": 7 * 86400}

_PLACEHOLDER = re.compile(r"\{\s*([A-Za-z0-9_ .-]+?)\s*\}")


def fill(template: str, values: dict, escape: bool) -> str:
    """Mail merge: replaces {name}, {marks}, ... with this recipient's values.

    Matching ignores case and spaces/underscores. Unknown placeholders stay as-is.
    """
    lookup = {re.sub(r"[\s_]+", "", k).lower(): str(v) for k, v in values.items()}

    def repl(m):
        key = re.sub(r"[\s_]+", "", m.group(1)).lower()
        if key not in lookup:
            return m.group(0)
        return html_lib.escape(lookup[key]) if escape else lookup[key]
    return _PLACEHOLDER.sub(repl, template)


def usage(conn=None) -> dict:
    close = conn is None
    conn = conn or db.connect()
    try:
        t = db.now()
        day = conn.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at > ?", (t - 86400,)).fetchone()[0]
        minute = conn.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at > ?", (t - 60,)).fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM messages WHERE status='pending'").fetchone()[0]
    finally:
        if close:
            conn.close()
    return {"sent_24h": day, "daily_limit": DAILY_LIMIT, "sent_last_minute": minute,
            "per_minute_limit": PER_MINUTE_LIMIT, "pending": pending}


def create_job(*, created_by, api_key_id, source, subject, body, html, reply_to,
               recipients, attachment_ids, scheduled_at, repeat) -> int:
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (created_by, api_key_id, source, subject, body, html, reply_to, recipients,"
            " attachment_ids, status, scheduled_at, repeat, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)",
            (created_by, api_key_id, source, subject, body, int(html), reply_to, json.dumps(recipients),
             json.dumps(attachment_ids), scheduled_at, repeat, db.now()),
        )
        return cur.lastrowid


def cancel_job(job_id: int):
    with db.tx() as conn:
        conn.execute("UPDATE messages SET status='cancelled' WHERE job_id=? AND status='pending'", (job_id,))
        conn.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE id=? AND status IN ('scheduled','sending')",
                     (db.now(), job_id))


def _open_due_jobs(conn):
    t = db.now()
    for job in conn.execute("SELECT * FROM jobs WHERE status='scheduled' AND scheduled_at <= ?", (t,)).fetchall():
        recipients = db.loads(job["recipients"], [])
        conn.executemany(
            "INSERT INTO messages (job_id, email, vars, next_attempt_at) VALUES (?, ?, ?, ?)",
            [(job["id"], r["email"], json.dumps(r.get("vars") or {}), t) for r in recipients],
        )
        conn.execute("UPDATE jobs SET status='sending' WHERE id=?", (job["id"],))
        step = REPEAT_SECONDS.get(job["repeat"])
        if step:
            nxt = job["scheduled_at"] + step
            while nxt <= t:  # server was off for a while: skip missed runs
                nxt += step
            conn.execute(
                "INSERT INTO jobs (created_by, api_key_id, source, subject, body, html, reply_to, recipients,"
                " attachment_ids, status, scheduled_at, repeat, parent_id, created_at)"
                " SELECT created_by, api_key_id, source, subject, body, html, reply_to, recipients,"
                " attachment_ids, 'scheduled', ?, repeat, ?, ? FROM jobs WHERE id=?",
                (nxt, job["id"], t, job["id"]),
            )
        log.log(log_level.INFO, "mail_queue.py", f"Job {job['id']} opened for {len(recipients)} recipient(s)")


def _load_attachments(conn, ids_json, cache):
    out = []
    for att_id in db.loads(ids_json, []):
        if att_id not in cache:
            row = conn.execute("SELECT * FROM attachments WHERE id=?", (att_id,)).fetchone()
            cache[att_id] = None if not row else {
                "filename": row["filename"], "content_type": row["content_type"],
                "data": Path(row["path"]).read_bytes(),
            }
        if cache[att_id]:
            out.append(cache[att_id])
    return out


def _send_pending(conn, doctor):
    u = usage(conn)
    room = min(BATCH_SIZE, DAILY_LIMIT - u["sent_24h"], PER_MINUTE_LIMIT - u["sent_last_minute"])
    if room <= 0:
        return 0
    batch = conn.execute(
        "SELECT m.*, j.subject, j.body, j.html, j.reply_to, j.attachment_ids FROM messages m"
        " JOIN jobs j ON j.id = m.job_id WHERE m.status='pending' AND m.next_attempt_at <= ?"
        " ORDER BY m.id LIMIT ?", (db.now(), room)).fetchall()
    if not batch:
        return 0

    att_cache = {}
    done = 0
    try:
        with doctor.session() as send:
            for m in batch:
                values = {"email": m["email"], **db.loads(m["vars"], {})}
                html = bool(m["html"])
                try:
                    msg = doctor.build(m["email"], fill(m["subject"], values, False), fill(m["body"], values, html),
                                       html, m["reply_to"], _load_attachments(conn, m["attachment_ids"], att_cache))
                    send(msg)
                    conn.execute("UPDATE messages SET status='sent', attempts=attempts+1, sent_at=?, last_error=NULL"
                                 " WHERE id=?", (db.now(), m["id"]))
                except Exception as err:
                    _record_failure(conn, m, err)
                conn.commit()
                done += 1
    except Exception as err:
        # Could not even connect / log in: every message in the batch gets a retry.
        log.log(log_level.ERROR, "mail_queue.py", f"SMTP connection failed: {err}")
        for m in batch[done:]:
            _record_failure(conn, m, err)
        conn.commit()
    return done


def _record_failure(conn, m, err):
    attempts = m["attempts"] + 1
    permanent = isinstance(err, smtplib.SMTPRecipientsRefused) and attempts >= 2
    text = _friendly(err)
    if attempts >= MAX_ATTEMPTS or permanent:
        conn.execute("UPDATE messages SET status='failed', attempts=?, last_error=? WHERE id=?",
                     (attempts, text, m["id"]))
        log.log(log_level.ERROR, "mail_queue.py", f"Gave up on {m['email']}: {text}")
    else:
        wait = 30 * (4 ** (attempts - 1))  # 30 s, 2 min, 8 min
        conn.execute("UPDATE messages SET attempts=?, last_error=?, next_attempt_at=? WHERE id=?",
                     (attempts, text, db.now() + wait, m["id"]))
        log.log(log_level.WARNING, "mail_queue.py", f"Retrying {m['email']} in {wait}s: {text}")


def _friendly(err) -> str:
    if isinstance(err, smtplib.SMTPAuthenticationError):
        return "Mail login failed. Check SENDER_EMAIL and SENDER_APP_PASSWORD."
    if isinstance(err, smtplib.SMTPRecipientsRefused):
        return "The mail server refused this address."
    if isinstance(err, (OSError, smtplib.SMTPServerDisconnected)):
        return f"Could not reach the mail server ({err})."
    return str(err)


def _close_finished_jobs(conn):
    for job in conn.execute("SELECT id FROM jobs WHERE status='sending'").fetchall():
        counts = dict(conn.execute("SELECT status, COUNT(*) FROM messages WHERE job_id=? GROUP BY status",
                                   (job["id"],)).fetchall())
        if counts.get("pending"):
            continue
        sent, failed = counts.get("sent", 0), counts.get("failed", 0)
        status = "done" if not failed else ("partial" if sent else "failed")
        conn.execute("UPDATE jobs SET status=?, finished_at=? WHERE id=?", (status, db.now(), job["id"]))


def process_once(doctor) -> int:
    """One pass of the queue. Returns how many messages were attempted."""
    conn = db.connect()
    try:
        with conn:
            _open_due_jobs(conn)
        attempted = _send_pending(conn, doctor)
        with conn:
            _close_finished_jobs(conn)
        return attempted
    finally:
        conn.close()


class QueueRunner(threading.Thread):
    def __init__(self, doctor):
        super().__init__(daemon=True, name="mail-queue")
        self.doctor = doctor
        self.stop_event = threading.Event()

    def run(self):
        log.log(log_level.INFO, "mail_queue.py",
                f"Queue running (limits: {DAILY_LIMIT}/day, {PER_MINUTE_LIMIT}/minute, {MAX_ATTEMPTS} attempts)")
        while not self.stop_event.is_set():
            try:
                process_once(self.doctor)
            except Exception as err:
                log.log(log_level.ERROR, "mail_queue.py", f"Queue error: {err}")
            self.stop_event.wait(TICK_SECONDS)

    def stop(self):
        self.stop_event.set()
