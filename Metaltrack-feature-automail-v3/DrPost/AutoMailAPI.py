import base64
import csv
import io
import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path: Path):
    """Minimal .env reader so secrets live outside the source code."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in ("'", '"') and value.count(value[0]) >= 2:
            value = value[1:value.index(value[0], 1)]            # quoted: keep everything inside the quotes
        else:
            value = re.split(r"(?:^|\s+)#", value, maxsplit=1)[0].strip()   # unquoted: drop a "# comment"
        os.environ.setdefault(key.strip(), value)


load_env_file(BASE_DIR / ".env")
load_env_file(BASE_DIR.parent / ".env")

import account_mail  # noqa: E402  (these read settings from the environment loaded above)
import auth  # noqa: E402
import db  # noqa: E402
import mail_queue  # noqa: E402
import Worker  # noqa: E402
from auth import Principal, current_admin, current_user, user_or_app  # noqa: E402
from logger import logger, log_level  # noqa: E402

log = logger()

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
MAX_RECIPIENTS = int(os.getenv("MAX_RECIPIENTS", "500"))
MAX_ATTACHMENT_MB = int(os.getenv("MAX_ATTACHMENT_MB", "10"))
RUN_QUEUE = os.getenv("RUN_QUEUE", "true").lower() in ("1", "true", "yes")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOW_SIGNUP = os.getenv("ALLOW_SIGNUP", "true").lower() in ("1", "true", "yes")
ALLOWED_EMAIL_DOMAINS = [d.strip().lower().lstrip("@") for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()]
PASSWORD_MIN = 8
# The address people open in their browser. Links in emails are built from it.
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/") or f"http://{os.getenv('HOST', '127.0.0.1')}:{os.getenv('PORT', '6767')}"

doctor = Worker.DrMail(
    SENDER_EMAIL,
    os.getenv("SENDER_APP_PASSWORD", "").replace(" ", ""),     # Google shows it as "xxxx xxxx xxxx xxxx"
    host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
    port=int(os.getenv("SMTP_PORT", "587")),
    sender_name=os.getenv("SENDER_NAME", "Dr. Post"),
    dry_run=DRY_RUN,
)


@asynccontextmanager
async def lifespan(app):
    db.init()
    auth.ensure_admin()
    runner = None
    if RUN_QUEUE:
        runner = mail_queue.QueueRunner(doctor)
        runner.start()
    yield
    if runner:
        runner.stop()


app = FastAPI(title="AutoMail", description="Automatic mail notification service", version="3.0",
              lifespan=lifespan)

# The web UI is served by this same app, so it needs no CORS. Other browser
# front ends must be listed in ALLOWED_ORIGINS (never "*": that would let any
# website send mail through this server).
if ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type", "Authorization", "X-API-Key"])

@app.middleware("http")
async def revalidate_ui_files(request, call_next):
    """Browsers re-check the UI files on each load, so an updated app.js is never stale."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def check_email(addr: str) -> str:
    addr = (addr or "").strip()
    if not EMAIL_RE.match(addr):
        raise ValueError(f"'{addr}' is not a valid email address")
    return addr


def split_addresses(value: Union[List[str], str, None]) -> List[str]:
    if not value:
        return []
    items = re.split(r"[,;\n]", value) if isinstance(value, str) else value
    return [check_email(i) for i in items if i and i.strip()]


# ======================================================================
# Models
# ======================================================================

class LoginIn(BaseModel):
    username: str                  # the username or the email address
    password: str


class SignupIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str
    password: str = Field(min_length=PASSWORD_MIN, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return check_email(v).lower()


class EmailIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return check_email(v).lower()


class ResendIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=200)   # username or email


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetIn(TokenIn):
    password: str = Field(min_length=PASSWORD_MIN, max_length=200)


class Recipient(BaseModel):
    email: str
    vars: Dict[str, str] = {}

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return check_email(v)


class SendIn(BaseModel):
    """One request = one job. Recipients can come from any mix of:
    `to` (addresses), `recipients` (addresses with mail-merge values, e.g. from a CSV)
    and `groups` (contact group names)."""
    to: Union[List[str], str, None] = None
    recipients: List[Recipient] = []
    groups: List[str] = []
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=100_000)
    html: bool = False
    reply_to: Optional[str] = None
    attachment_ids: List[int] = []
    send_at: Union[int, str, None] = Field(default=None, description="Unix time or ISO 8601. Empty = now.")
    repeat: str = Field(default="none", pattern="^(none|daily|weekly)$")

    @field_validator("to")
    @classmethod
    def _to(cls, v):
        return split_addresses(v)

    @field_validator("reply_to")
    @classmethod
    def _reply_to(cls, v):
        return check_email(v) if v else None


class LegacyMail(BaseModel):
    """Payload of the original /send_mail and /send_multiple_mail endpoints."""
    to: Union[List[str], str]
    sub: str = Field(min_length=1, max_length=200)
    msg_content: str = Field(min_length=1, max_length=100_000)
    html: bool = False
    reply_to: Optional[str] = None


class ContactIn(BaseModel):
    name: str = Field(default="", max_length=120)
    email: str
    groups: List[str] = []
    extra: Dict[str, str] = {}

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return check_email(v)


class CsvIn(BaseModel):
    csv: str = Field(max_length=5_000_000)


class ImportIn(CsvIn):
    group: Optional[str] = None


class AttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_type: str = "application/octet-stream"
    data_base64: str


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=PASSWORD_MIN, max_length=200)
    role: str = Field(default="sender", pattern="^(admin|sender)$")


class PasswordIn(BaseModel):
    password: str = Field(min_length=PASSWORD_MIN, max_length=200)


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


# ======================================================================
# Helpers
# ======================================================================

def parse_send_at(value) -> int:
    if value in (None, "", 0):
        return db.now()
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        ts = int(value)
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, "send_at must be a Unix time or an ISO date like 2026-11-23T09:00:00+05:30.")
        if dt.tzinfo is None:
            dt = dt.astimezone()  # treat as server local time
        ts = int(dt.timestamp())
    if ts > db.now() + 366 * 86400:
        raise HTTPException(422, "send_at can be at most one year ahead.")
    return max(ts, db.now())


def group_recipients(conn, names: List[str]) -> List[dict]:
    out = []
    for name in names:
        group = conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()
        if not group:
            raise HTTPException(404, f"There is no contact group called '{name}'.")
        for c in conn.execute(
                "SELECT c.* FROM contacts c JOIN contact_groups cg ON cg.contact_id = c.id WHERE cg.group_id = ?",
                (group["id"],)):
            out.append({"email": c["email"], "vars": {"name": c["name"], **db.loads(c["extra"], {})}})
    return out


def create_send_job(data: SendIn, who: Principal, source: str) -> dict:
    with db.tx() as conn:
        merged = [{"email": a, "vars": {}} for a in split_addresses(data.to)]
        merged += [r.model_dump() for r in data.recipients]
        merged += group_recipients(conn, data.groups)
        for att_id in data.attachment_ids:
            if not conn.execute("SELECT 1 FROM attachments WHERE id = ?", (att_id,)).fetchone():
                raise HTTPException(404, f"Attachment {att_id} does not exist. Upload it again.")

    seen, recipients = set(), []
    for r in merged:  # keep the first entry for each address (it may carry merge values)
        key = r["email"].lower()
        if key not in seen:
            seen.add(key)
            recipients.append(r)
    if not recipients:
        raise HTTPException(422, "Add at least one recipient.")
    if len(recipients) > MAX_RECIPIENTS:
        raise HTTPException(422, f"At most {MAX_RECIPIENTS} recipients per send.")

    scheduled_at = parse_send_at(data.send_at)
    if data.repeat != "none" and data.send_at in (None, ""):
        raise HTTPException(422, "Pick a first send time for repeating mail.")

    job_id = mail_queue.create_job(
        created_by=who.user_id, api_key_id=who.api_key_id, source=source, subject=data.subject, body=data.body,
        html=data.html, reply_to=data.reply_to, recipients=recipients, attachment_ids=data.attachment_ids,
        scheduled_at=scheduled_at, repeat=data.repeat)
    return {"job_id": job_id, "recipients": len(recipients), "scheduled_at": scheduled_at,
            "repeat": data.repeat, "dry_run": DRY_RUN,
            "status": "scheduled" if scheduled_at > db.now() + 5 else "queued"}


def job_visible(job, who: Principal) -> bool:
    if who.is_admin:
        return True
    if who.role == "app":
        return job["api_key_id"] == who.api_key_id
    return job["created_by"] == who.user_id


def job_summary(conn, job) -> dict:
    counts = dict(conn.execute("SELECT status, COUNT(*) FROM messages WHERE job_id = ? GROUP BY status",
                               (job["id"],)).fetchall())
    total = len(db.loads(job["recipients"], []))
    creator = None
    if job["created_by"]:
        u = conn.execute("SELECT username FROM users WHERE id = ?", (job["created_by"],)).fetchone()
        creator = u["username"] if u else None
    elif job["api_key_id"]:
        k = conn.execute("SELECT name FROM api_keys WHERE id = ?", (job["api_key_id"],)).fetchone()
        creator = f"app: {k['name']}" if k else "app"
    return {
        "id": job["id"], "subject": job["subject"], "status": job["status"], "source": job["source"],
        "scheduled_at": job["scheduled_at"], "repeat": job["repeat"], "created_at": job["created_at"],
        "finished_at": job["finished_at"], "created_by": creator, "html": bool(job["html"]),
        "attachments": len(db.loads(job["attachment_ids"], [])),
        "total": total, "sent": counts.get("sent", 0), "failed": counts.get("failed", 0),
        "pending": counts.get("pending", 0), "cancelled": counts.get("cancelled", 0),
    }


def read_csv(text: str):
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise HTTPException(422, "The CSV is empty.")
    columns = [c.strip() for c in reader.fieldnames if c and c.strip()]
    email_col = next((c for c in columns if c.lower() in ("email", "e-mail", "mail", "email address", "email_id")), None)
    if not email_col:
        raise HTTPException(422, "The CSV needs a column called 'email'.")
    rows, skipped = [], []
    for i, raw in enumerate(reader, start=2):
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
        email = row.get(email_col, "")
        if not EMAIL_RE.match(email):
            if any(row.values()):
                skipped.append({"line": i, "email": email, "reason": "invalid email"})
            continue
        rows.append({"email": email, "vars": {k: v for k, v in row.items() if k != email_col}})
    return columns, email_col, rows, skipped


# ======================================================================
# Pages and health
# ======================================================================

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)  # the page sets its own inline icon


@app.get("/health")
def health():
    return {"status": "ok", "dry_run": DRY_RUN, "sender": SENDER_EMAIL or None, **mail_queue.usage()}


# ======================================================================
# Login, users, API keys
# ======================================================================

def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.get("/api/config")
def api_config():
    """What the sign-in page needs to know before anyone is logged in."""
    return {"signup": ALLOW_SIGNUP, "email_domains": ALLOWED_EMAIL_DOMAINS, "dry_run": DRY_RUN,
            "password_min": PASSWORD_MIN}


@app.post("/api/login")
def api_login(data: LoginIn):
    return auth.login(data.username.strip(), data.password)


@app.post("/api/signup")
def api_signup(data: SignupIn, request: Request, background: BackgroundTasks):
    """Creates an account that stays locked until the emailed link is opened."""
    is_admin_address = data.email == auth.admin_email()
    if not ALLOW_SIGNUP and not is_admin_address:
        raise HTTPException(403, "Sign-up is closed. Ask an admin to create your account.")
    if ALLOWED_EMAIL_DOMAINS and not is_admin_address and data.email.rsplit("@", 1)[1] not in ALLOWED_EMAIL_DOMAINS:
        raise HTTPException(403, "Use your organisation's email address (" + ", ".join("@" + d for d in ALLOWED_EMAIL_DOMAINS) + ").")
    auth.rate_limit("signup-ip", _ip(request), 5, 3600)
    token = auth.signup(data.username, data.email, data.password)
    background.add_task(account_mail.verification, doctor, data.email, data.username, f"{PUBLIC_URL}/#/verify/{token}")
    return {"ok": True, "dry_run": DRY_RUN}


@app.post("/api/verify-email")
def api_verify_email(data: TokenIn):
    return {"ok": True, "username": auth.verify_email(data.token)}


@app.post("/api/resend-verification")
def api_resend_verification(data: ResendIn, request: Request, background: BackgroundTasks):
    """Same answer whether or not the account exists, so it can't be used to look people up."""
    auth.rate_limit("resend-ip", _ip(request), 10, 3600)
    auth.rate_limit("resend", data.identifier, 1, 60)
    found = auth.resend_verification(data.identifier.strip())
    if found:
        email, token = found
        background.add_task(account_mail.verification, doctor, email, email.split("@")[0], f"{PUBLIC_URL}/#/verify/{token}")
    return {"ok": True, "dry_run": DRY_RUN}


@app.post("/api/forgot-password")
def api_forgot_password(data: EmailIn, request: Request, background: BackgroundTasks):
    """Same answer whether or not the address has an account."""
    auth.rate_limit("forgot-ip", _ip(request), 10, 3600)
    auth.rate_limit("forgot", data.email, 3, 3600)
    found = auth.start_reset(data.email)
    if found:
        username, token = found
        background.add_task(account_mail.password_reset, doctor, data.email, username, f"{PUBLIC_URL}/#/reset/{token}")
    return {"ok": True, "dry_run": DRY_RUN}


@app.post("/api/reset-password")
def api_reset_password_with_token(data: ResetIn, request: Request):
    auth.rate_limit("reset-ip", _ip(request), 20, 3600)
    auth.reset_password(data.token, data.password)
    return {"ok": True}


@app.post("/api/logout")
def api_logout(authorization: Optional[str] = Header(default=None), who: Principal = Depends(current_user)):
    auth.logout(authorization[7:].strip())
    return {"ok": True}


@app.get("/api/me")
def api_me(who: Principal = Depends(current_user)):
    with db.tx() as conn:
        email = conn.execute("SELECT email FROM users WHERE id = ?", (who.user_id,)).fetchone()["email"]
    return {"id": who.user_id, "username": who.username, "email": email, "role": who.role,
            "dry_run": DRY_RUN, "sender": SENDER_EMAIL or None, "max_recipients": MAX_RECIPIENTS,
            "max_attachment_mb": MAX_ATTACHMENT_MB}


@app.post("/api/me/password")
def api_change_password(data: PasswordIn, who: Principal = Depends(current_user)):
    with db.tx() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (auth.hash_password(data.password), who.user_id))
    return {"ok": True}


@app.get("/api/users")
def api_users(who: Principal = Depends(current_admin)):
    with db.tx() as conn:
        return db.rows(conn.execute("SELECT id, username, role, created_at FROM users ORDER BY username"))


@app.post("/api/users")
def api_add_user(data: UserIn, who: Principal = Depends(current_admin)):
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (data.username,)).fetchone():
            raise HTTPException(409, f"The username '{data.username}' is taken.")
        cur = conn.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                           (data.username, auth.hash_password(data.password), data.role, db.now()))
    return {"id": cur.lastrowid, "username": data.username, "role": data.role}


@app.post("/api/users/{user_id}/password")
def api_reset_password(user_id: int, data: PasswordIn, who: Principal = Depends(current_admin)):
    with db.tx() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (auth.hash_password(data.password), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"ok": True}


@app.delete("/api/users/{user_id}")
def api_delete_user(user_id: int, who: Principal = Depends(current_admin)):
    if user_id == who.user_id:
        raise HTTPException(400, "You can't delete your own account.")
    with db.tx() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"ok": True}


@app.get("/api/keys")
def api_keys(who: Principal = Depends(current_admin)):
    with db.tx() as conn:
        return db.rows(conn.execute(
            "SELECT id, name, prefix, created_at, last_used_at FROM api_keys WHERE revoked = 0 ORDER BY id DESC"))


@app.post("/api/keys")
def api_add_key(data: KeyIn, who: Principal = Depends(current_admin)):
    return auth.create_api_key(data.name.strip(), who.user_id)


@app.delete("/api/keys/{key_id}")
def api_revoke_key(key_id: int, who: Principal = Depends(current_admin)):
    with db.tx() as conn:
        conn.execute("UPDATE api_keys SET revoked = 1 WHERE id = ?", (key_id,))
    return {"ok": True}


# ======================================================================
# Contacts and groups
# ======================================================================

def _set_groups(conn, contact_id: int, names: List[str]):
    conn.execute("DELETE FROM contact_groups WHERE contact_id = ?", (contact_id,))
    for name in {n.strip() for n in names if n.strip()}:
        conn.execute("INSERT OR IGNORE INTO groups (name) VALUES (?)", (name,))
        gid = conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()["id"]
        conn.execute("INSERT OR IGNORE INTO contact_groups (contact_id, group_id) VALUES (?, ?)", (contact_id, gid))


@app.get("/api/contacts")
def api_contacts(q: str = "", group: str = "", who: Principal = Depends(current_user)):
    sql = ("SELECT c.*, GROUP_CONCAT(g.name, '|') AS group_names FROM contacts c"
           " LEFT JOIN contact_groups cg ON cg.contact_id = c.id LEFT JOIN groups g ON g.id = cg.group_id")
    where, params = [], []
    if q:
        where.append("(c.name LIKE ? OR c.email LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if group:
        where.append("c.id IN (SELECT cg2.contact_id FROM contact_groups cg2 JOIN groups g2 ON g2.id = cg2.group_id"
                     " WHERE g2.name = ?)")
        params.append(group)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY c.id ORDER BY c.name COLLATE NOCASE, c.email LIMIT 1000"
    with db.tx() as conn:
        out = []
        for r in conn.execute(sql, params):
            out.append({"id": r["id"], "name": r["name"], "email": r["email"], "extra": db.loads(r["extra"], {}),
                        "groups": sorted(filter(None, (r["group_names"] or "").split("|")))})
        return out


@app.post("/api/contacts")
def api_add_contact(data: ContactIn, who: Principal = Depends(current_user)):
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM contacts WHERE email = ?", (data.email,)).fetchone():
            raise HTTPException(409, f"{data.email} is already in your contacts.")
        cur = conn.execute("INSERT INTO contacts (name, email, extra, created_at) VALUES (?, ?, ?, ?)",
                           (data.name.strip(), data.email, json.dumps(data.extra), db.now()))
        _set_groups(conn, cur.lastrowid, data.groups)
    return {"id": cur.lastrowid}


@app.put("/api/contacts/{contact_id}")
def api_edit_contact(contact_id: int, data: ContactIn, who: Principal = Depends(current_user)):
    with db.tx() as conn:
        clash = conn.execute("SELECT id FROM contacts WHERE email = ? AND id != ?", (data.email, contact_id)).fetchone()
        if clash:
            raise HTTPException(409, f"{data.email} belongs to another contact.")
        conn.execute("UPDATE contacts SET name = ?, email = ?, extra = ? WHERE id = ?",
                     (data.name.strip(), data.email, json.dumps(data.extra), contact_id))
        _set_groups(conn, contact_id, data.groups)
    return {"ok": True}


@app.delete("/api/contacts/{contact_id}")
def api_delete_contact(contact_id: int, who: Principal = Depends(current_user)):
    with db.tx() as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.execute("DELETE FROM groups WHERE id NOT IN (SELECT group_id FROM contact_groups)")
    return {"ok": True}


@app.post("/api/contacts/import")
def api_import_contacts(data: ImportIn, who: Principal = Depends(current_user)):
    """CSV with an 'email' column; 'name' and any other columns are kept for mail merge."""
    _, _, rows, skipped = read_csv(data.csv)
    added = updated = 0
    with db.tx() as conn:
        for r in rows:
            v = dict(r["vars"])
            name = v.pop("name", v.pop("Name", ""))
            existing = conn.execute("SELECT id, extra FROM contacts WHERE email = ?", (r["email"],)).fetchone()
            if existing:
                extra = {**db.loads(existing["extra"], {}), **v}
                conn.execute("UPDATE contacts SET name = COALESCE(NULLIF(?, ''), name), extra = ? WHERE id = ?",
                             (name, json.dumps(extra), existing["id"]))
                cid = existing["id"]
                updated += 1
            else:
                cid = conn.execute("INSERT INTO contacts (name, email, extra, created_at) VALUES (?, ?, ?, ?)",
                                   (name, r["email"], json.dumps(v), db.now())).lastrowid
                added += 1
            if data.group and data.group.strip():
                current = [g["name"] for g in conn.execute(
                    "SELECT g.name FROM groups g JOIN contact_groups cg ON cg.group_id = g.id WHERE cg.contact_id = ?",
                    (cid,))]
                _set_groups(conn, cid, current + [data.group.strip()])
    return {"added": added, "updated": updated, "skipped": skipped}


@app.get("/api/groups")
def api_groups(who: Principal = Depends(current_user)):
    with db.tx() as conn:
        return db.rows(conn.execute(
            "SELECT g.id, g.name, COUNT(cg.contact_id) AS members FROM groups g"
            " LEFT JOIN contact_groups cg ON cg.group_id = g.id GROUP BY g.id ORDER BY g.name COLLATE NOCASE"))


@app.delete("/api/groups/{group_id}")
def api_delete_group(group_id: int, who: Principal = Depends(current_user)):
    with db.tx() as conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    return {"ok": True}


# ======================================================================
# CSV mail merge and attachments
# ======================================================================

@app.post("/api/csv/parse")
def api_parse_csv(data: CsvIn, who: Principal = Depends(current_user)):
    columns, email_col, rows, skipped = read_csv(data.csv)
    if len(rows) > MAX_RECIPIENTS:
        raise HTTPException(422, f"The CSV has {len(rows)} rows; the limit is {MAX_RECIPIENTS}.")
    return {"columns": columns, "email_column": email_col, "rows": rows, "skipped": skipped}


@app.post("/api/attachments")
def api_upload(data: AttachmentIn, who: Principal = Depends(user_or_app)):
    try:
        raw = base64.b64decode(data.data_base64, validate=True)
    except ValueError:
        raise HTTPException(422, "data_base64 is not valid base64.")
    if len(raw) > MAX_ATTACHMENT_MB * 1024 * 1024:
        raise HTTPException(413, f"Attachments can be at most {MAX_ATTACHMENT_MB} MB.")
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(data.filename).name)[:120] or "file"
    path = db.ATTACHMENT_DIR / f"{secrets.token_hex(8)}_{safe}"
    path.write_bytes(raw)
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO attachments (filename, content_type, size, path, uploaded_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (safe, data.content_type or "application/octet-stream", len(raw), str(path), who.user_id, db.now()))
    return {"id": cur.lastrowid, "filename": safe, "size": len(raw)}


# ======================================================================
# Sending, jobs, stats
# ======================================================================

@app.post("/api/send")
def api_send(data: SendIn, who: Principal = Depends(user_or_app)):
    """Queues a mail. Also the webhook for other apps: send it with an X-API-Key header."""
    return create_send_job(data, who, "ui" if who.user_id else "webhook")


@app.post("/send_mail", tags=["legacy"])
def send_mail(data: LegacyMail, who: Principal = Depends(user_or_app)):
    to = split_addresses(data.to)[:1]
    return create_send_job(SendIn(to=to, subject=data.sub, body=data.msg_content, html=data.html,
                                  reply_to=data.reply_to), who, "api")


@app.post("/send_multiple_mail", tags=["legacy"])
def send_multiple_mail(data: LegacyMail, who: Principal = Depends(user_or_app)):
    return create_send_job(SendIn(to=data.to, subject=data.sub, body=data.msg_content, html=data.html,
                                  reply_to=data.reply_to), who, "api")


@app.get("/api/jobs")
def api_jobs(limit: int = 50, who: Principal = Depends(user_or_app)):
    limit = max(1, min(limit, 200))
    with db.tx() as conn:
        if who.is_admin:
            jobs = conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        elif who.role == "app":
            jobs = conn.execute("SELECT * FROM jobs WHERE api_key_id = ? ORDER BY id DESC LIMIT ?",
                                (who.api_key_id, limit)).fetchall()
        else:
            jobs = conn.execute("SELECT * FROM jobs WHERE created_by = ? ORDER BY id DESC LIMIT ?",
                                (who.user_id, limit)).fetchall()
        return [job_summary(conn, j) for j in jobs]


def _get_job(conn, job_id: int, who: Principal):
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job or not job_visible(job, who):
        raise HTTPException(404, "No such job.")
    return job


@app.get("/api/jobs/{job_id}")
def api_job(job_id: int, who: Principal = Depends(user_or_app)):
    with db.tx() as conn:
        job = _get_job(conn, job_id, who)
        out = job_summary(conn, job)
        out["body"] = job["body"]
        out["reply_to"] = job["reply_to"]
        msgs = db.rows(conn.execute(
            "SELECT email, status, attempts, last_error, sent_at, next_attempt_at FROM messages WHERE job_id = ?"
            " ORDER BY id", (job_id,)))
        if not msgs:  # not opened yet: list the planned recipients
            msgs = [{"email": r["email"], "status": job["status"] if job["status"] == "cancelled" else "scheduled",
                     "attempts": 0, "last_error": None, "sent_at": None, "next_attempt_at": None}
                    for r in db.loads(job["recipients"], [])]
        out["messages"] = msgs
        return out


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel(job_id: int, who: Principal = Depends(user_or_app)):
    with db.tx() as conn:
        job = _get_job(conn, job_id, who)
        if job["status"] not in ("scheduled", "sending"):
            raise HTTPException(409, "This job has already finished.")
    mail_queue.cancel_job(job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/retry")
def api_retry(job_id: int, who: Principal = Depends(user_or_app)):
    with db.tx() as conn:
        _get_job(conn, job_id, who)
        n = conn.execute("UPDATE messages SET status = 'pending', attempts = 0, next_attempt_at = ?"
                         " WHERE job_id = ? AND status = 'failed'", (db.now(), job_id)).rowcount
        if not n:
            raise HTTPException(409, "There are no failed messages to retry.")
        conn.execute("UPDATE jobs SET status = 'sending', finished_at = NULL WHERE id = ?", (job_id,))
    return {"retrying": n}


@app.get("/api/stats")
def api_stats(days: int = 14, tz_offset_minutes: int = 0, who: Principal = Depends(current_user)):
    """Sent / failed per day for the last `days` days, in the viewer's time zone."""
    days = max(1, min(days, 90))
    shift = tz_offset_minutes * 60
    today_local = (db.now() + shift) // 86400
    start_day = today_local - days + 1
    with db.tx() as conn:
        sent = dict(conn.execute(
            "SELECT (sent_at + ?) / 86400 AS d, COUNT(*) FROM messages WHERE status = 'sent' AND (sent_at + ?) / 86400 >= ?"
            " GROUP BY d", (shift, shift, start_day)).fetchall())
        # A failed message has no sent_at; use its last attempt time (next_attempt_at is set when it was tried).
        failed = dict(conn.execute(
            "SELECT (next_attempt_at + ?) / 86400 AS d, COUNT(*) FROM messages WHERE status = 'failed'"
            " AND (next_attempt_at + ?) / 86400 >= ? GROUP BY d", (shift, shift, start_day)).fetchall())
        totals = dict(conn.execute("SELECT status, COUNT(*) FROM messages GROUP BY status").fetchall())
        scheduled = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'scheduled'").fetchone()[0]
        contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        usage = mail_queue.usage(conn)
    series = []
    for d in range(start_day, today_local + 1):
        date = datetime.fromtimestamp(d * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
        series.append({"date": date, "sent": sent.get(d, 0), "failed": failed.get(d, 0)})
    return {"days": series, "total_sent": totals.get("sent", 0), "total_failed": totals.get("failed", 0),
            "pending": totals.get("pending", 0), "scheduled_jobs": scheduled, "contacts": contacts, "usage": usage}


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "6767")))
