# AutoMail

Automatic mail notification service. A FastAPI server ("Dr. Post") queues,
schedules and sends mail through Gmail SMTP. People use the web UI or the
command-line client. Other apps send notifications through the same API with
an API key (webhook).

```
 Web UI / CLI ──(login)──┐
                         ├─▶ AutoMailAPI (FastAPI) ──▶ SQLite ◀── mail_queue (background thread) ──SMTP/TLS──▶ Gmail
 Other apps ──(API key)──┘     validation, roles,        jobs,       scheduling, retries,
                               mail merge, stats         messages    rate limits
```

## Features

| Feature | Where |
|---|---|
| **Scheduled and recurring mail**: send later, or repeat daily/weekly. Survives restarts. | Compose › Delivery |
| **Contacts and groups** (e.g. `CSE-A`), CSV import | Contacts |
| **Mail merge**: upload a CSV and use `{name}`, `{marks}`, any column, in the subject or body | Compose › Import CSV |
| **Attachments** (PDFs, circulars…), up to 10 MB each | Compose › Attachments |
| **Background queue with retries**: failed addresses are retried after 30 s, 2 min, 8 min | Outbox (live progress) |
| **Rate limiting**: max per minute and per 24 hours (Gmail allows ~500/day) | Dashboard, postmark in the sidebar |
| **Login with roles**: *admin* (everything) and *sender* (compose, contacts, own outbox) | Settings |
| **Dashboard**: sent vs failed per day, totals, quota | Dashboard |
| **Webhook for other apps**: create an API key, then `POST /api/send` | Settings › Connected apps |
| **CI**: GitHub Actions runs the tests on every push | `.github/workflows/tests.yml` |
| Plain text or HTML with live preview, templates, Reply-To | Compose |

## Setup

1. Install Python 3.10+ and the dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` (project root or `DrPost/`) and fill it in.
   Gmail needs an **App Password**, not your normal password:
   Google Account → Security → 2-Step Verification → App passwords.
   Set `SENDER_EMAIL`, `SENDER_APP_PASSWORD`, `DRY_RUN=false` and `ADMIN_EMAIL`.
3. Start the server:
   ```
   python DrPost/AutoMailAPI.py
   ```
4. Open http://127.0.0.1:6767 and **Create an account** with the `ADMIN_EMAIL` address.
   Open the confirmation link from your inbox and you are the admin. No password is
   stored in any file. API docs: http://127.0.0.1:6767/docs

### Accounts

- **Sign up** with username, email and password (8+ characters). The account stays locked
  until the emailed confirmation link (valid 24 hours, works once) is opened.
- **Sign in** with the username or the email. **Forgot password** emails a one-hour,
  single-use link; using it signs the account out everywhere.
- The address in `ADMIN_EMAIL` becomes admin once confirmed. Everyone else is a *sender*.
  Admins can still add people by hand under Settings.
- `ALLOW_SIGNUP=false` closes public sign-up. `ALLOWED_EMAIL_DOMAINS=college.edu` limits it
  to your organisation. **If the server is reachable by strangers, set one of these:** every
  confirmation email and everything a sender sends uses your Gmail account's daily quota.
- Sign-up, resend and reset are rate limited per address. `PUBLIC_URL` must be the address people
  use in their browser, because the links in emails are built from it.

**Demo without a mail account:** set `DRY_RUN=true`. Mail is logged instead of
sent (confirmation and reset links are printed in the server window), and any address
ending in `@fail.test` fails on purpose so you can show retries and partial failures.

Command-line client (while the server runs):
```
python mailrunner/ServiceInvoker/ServiceInvoker.py
```

Docker (data is kept in a volume):
```
docker compose up --build
```

## API for other apps (webhook)

Create a key under **Settings › Connected apps**, then:

```
curl -X POST http://127.0.0.1:6767/api/send \
  -H "X-API-Key: am_..." -H "Content-Type: application/json" \
  -d '{"to": "team@example.com", "subject": "Sprint 4 is done", "body": "All stories are closed."}'
```

Optional fields: `send_at` (ISO time or Unix time), `repeat` (`daily`/`weekly`),
`groups` (contact group names), `recipients` (`[{"email": ..., "vars": {"name": ...}}]`
for mail merge), `html`, `reply_to`, `attachment_ids`. Check progress with
`GET /api/jobs/{job_id}`.

| Method | Path | Who |
|---|---|---|
| POST | `/api/login`, `/api/logout` | anyone / signed in |
| POST | `/api/signup`, `/api/verify-email`, `/api/resend-verification`, `/api/forgot-password`, `/api/reset-password` | anyone |
| GET | `/api/config` | anyone |
| POST | `/api/send` | user or API key |
| GET | `/api/jobs`, `/api/jobs/{id}` | user or API key |
| POST | `/api/jobs/{id}/cancel`, `/api/jobs/{id}/retry` | user or API key |
| GET/POST/PUT/DELETE | `/api/contacts`, `/api/contacts/import`, `/api/groups` | user |
| POST | `/api/csv/parse`, `/api/attachments` | user (attachments: API key too) |
| GET | `/api/stats` | user |
| GET/POST/DELETE | `/api/users`, `/api/keys` | admin |
| GET | `/health` | public |

The original `/send_mail` and `/send_multiple_mail` endpoints still work. They now need a login or API key and queue the mail.

## Project layout

```
DrPost/
  AutoMailAPI.py   API routes and request validation
  auth.py          users, roles, sessions, API keys, sign-up / email confirmation / reset tokens
  account_mail.py  the confirmation and password-reset emails
  db.py            SQLite schema and helpers
  mail_queue.py    scheduler, retries, rate limits, mail merge
  Worker.py        builds and sends messages over SMTP (or dry run)
  logger.py        coloured console logging
  static/          web UI (index.html, app.css, app.js - no build step)
mailrunner/ServiceInvoker/ServiceInvoker.py   command-line client
tests/             pytest suite (runs in dry-run mode)
```

## Tests

```
pytest
```
36 tests cover sign-up, email confirmation, password reset, login and roles, sending, retries,
scheduling, recurring jobs, cancelling, the daily limit, mail merge, CSV import, groups,
attachments, API keys, the legacy endpoints and stats. They never send real mail.
