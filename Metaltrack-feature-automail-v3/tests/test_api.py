"""Run with:  pytest   (dry-run mode: no real mail is sent)"""
import base64
import time

import db
import mail_queue


def send(client, headers, **body):
    body.setdefault("subject", "Hi")
    body.setdefault("body", "Hello")
    return client.post("/api/send", json=body, headers=headers)


# ---------- auth and roles ----------

def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["dry_run"] is True


def test_ui_is_served(client):
    assert "AutoMail" in client.get("/").text


def test_wrong_password(client):
    assert client.post("/api/login", json={"username": "admin", "password": "nope"}).status_code == 401


def test_send_needs_login(client):
    assert client.post("/api/send", json={"to": "a@example.com", "subject": "x", "body": "y"}).status_code == 401


def test_sender_cannot_manage_users(client, admin):
    client.post("/api/users", json={"username": "teacher", "password": "secret-pass-1", "role": "sender"}, headers=admin)
    tok = client.post("/api/login", json={"username": "teacher", "password": "secret-pass-1"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/me", headers=h).json()["role"] == "sender"
    assert client.get("/api/users", headers=h).status_code == 403
    assert send(client, h, to="x@example.com").status_code == 200


# ---------- sending ----------

def test_send_now_is_delivered(client, admin, run_queue):
    job = send(client, admin, to="a@example.com, b@example.com").json()
    run_queue()
    j = client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()
    assert j["status"] == "done" and j["sent"] == 2


def test_invalid_email_rejected(client, admin):
    assert send(client, admin, to="not-an-email").status_code == 422


def test_duplicates_removed(client, admin):
    r = send(client, admin, to=["a@example.com", "A@example.com"]).json()
    assert r["recipients"] == 1


def test_failed_address_is_retried_then_marked_failed(client, admin, run_queue):
    job = send(client, admin, to="ok@example.com, broken@fail.test").json()
    run_queue()
    with db.tx() as conn:  # skip the retry wait
        conn.execute("UPDATE messages SET next_attempt_at = 0 WHERE status = 'pending'")
    run_queue()
    j = client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()
    assert j["status"] == "partial" and j["sent"] == 1 and j["failed"] == 1
    bad = [m for m in j["messages"] if m["status"] == "failed"][0]
    assert bad["attempts"] == 2 and bad["last_error"]


def test_scheduled_mail_waits_then_sends(client, admin, run_queue):
    later = int(time.time()) + 3600
    job = send(client, admin, to="s@example.com", send_at=later).json()
    assert job["status"] == "scheduled"
    run_queue()
    assert client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()["status"] == "scheduled"
    with db.tx() as conn:
        conn.execute("UPDATE jobs SET scheduled_at = 0 WHERE id = ?", (job["job_id"],))
    run_queue()
    assert client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()["status"] == "done"


def test_recurring_mail_books_next_run(client, admin, run_queue):
    first = int(time.time()) + 60
    job = send(client, admin, to="r@example.com", send_at=first, repeat="daily").json()
    with db.tx() as conn:
        conn.execute("UPDATE jobs SET scheduled_at = ? WHERE id = ?", (int(time.time()) - 1, job["job_id"]))
    run_queue()
    with db.tx() as conn:
        nxt = conn.execute("SELECT * FROM jobs WHERE parent_id = ?", (job["job_id"],)).fetchone()
    assert nxt["status"] == "scheduled" and nxt["repeat"] == "daily"
    assert nxt["scheduled_at"] > time.time() + 80000


def test_cancel_scheduled(client, admin):
    job = send(client, admin, to="c@example.com", send_at=int(time.time()) + 3600).json()
    assert client.post(f"/api/jobs/{job['job_id']}/cancel", headers=admin).status_code == 200
    assert client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()["status"] == "cancelled"


def test_daily_limit_holds_mail(client, admin, run_queue, monkeypatch):
    monkeypatch.setattr(mail_queue, "DAILY_LIMIT", 0)
    job = send(client, admin, to="q@example.com").json()
    run_queue()
    j = client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()
    assert j["status"] == "sending" and j["pending"] == 1
    monkeypatch.setattr(mail_queue, "DAILY_LIMIT", 450)
    run_queue()
    assert client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()["status"] == "done"


# ---------- mail merge, contacts, attachments ----------

def test_fill_placeholders():
    assert mail_queue.fill("Hi {name}, marks: { Marks }", {"name": "Asha", "marks": "91"}, False) == "Hi Asha, marks: 91"
    assert mail_queue.fill("{name} {unknown}", {"name": "<b>"}, True) == "&lt;b&gt; {unknown}"


def test_csv_parse(client, admin):
    r = client.post("/api/csv/parse", json={"csv": "name,email,marks\nAsha,asha@example.com,91\nBad,nope,10\n"},
                    headers=admin).json()
    assert r["rows"] == [{"email": "asha@example.com", "vars": {"name": "Asha", "marks": "91"}}]
    assert r["skipped"][0]["email"] == "nope"


def test_contacts_groups_and_group_send(client, admin, run_queue):
    client.post("/api/contacts/import", headers=admin,
                json={"csv": "name,email,roll\nRavi,ravi@example.com,7\nMeena,meena@example.com,8", "group": "CSE-A"})
    groups = {g["name"]: g["members"] for g in client.get("/api/groups", headers=admin).json()}
    assert groups["CSE-A"] == 2
    job = send(client, admin, groups=["CSE-A"], subject="Roll {roll}").json()
    assert job["recipients"] == 2
    run_queue()
    assert client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()["sent"] == 2


def test_attachment_upload_and_send(client, admin, run_queue):
    data = base64.b64encode(b"%PDF-1.4 fake").decode()
    att = client.post("/api/attachments", headers=admin,
                      json={"filename": "circular.pdf", "content_type": "application/pdf", "data_base64": data}).json()
    job = send(client, admin, to="f@example.com", attachment_ids=[att["id"]]).json()
    run_queue()
    assert client.get(f"/api/jobs/{job['job_id']}", headers=admin).json()["status"] == "done"


# ---------- webhook / API keys, legacy endpoints, stats ----------

def test_webhook_with_api_key(client, admin, run_queue):
    key = client.post("/api/keys", json={"name": "agile-app"}, headers=admin).json()["key"]
    h = {"X-API-Key": key}
    job = client.post("/api/send", headers=h, json={"to": "w@example.com", "subject": "Sprint", "body": "Done"}).json()
    run_queue()
    assert client.get(f"/api/jobs/{job['job_id']}", headers=h).json()["status"] == "done"
    assert client.post("/api/send", headers={"X-API-Key": "am_wrong"},
                       json={"to": "w@example.com", "subject": "x", "body": "y"}).status_code == 401


def test_legacy_endpoint_still_works(client, admin):
    r = client.post("/send_multiple_mail", headers=admin,
                    json={"from": "x@y.com", "to": "a@example.com, b@example.com", "sub": "Hi", "msg_content": "Hey"})
    assert r.status_code == 200 and r.json()["recipients"] == 2


def test_stats(client, admin):
    s = client.get("/api/stats?days=7&tz_offset_minutes=330", headers=admin).json()
    assert len(s["days"]) == 7 and s["total_sent"] > 0
    assert sum(d["sent"] for d in s["days"]) == s["total_sent"]
