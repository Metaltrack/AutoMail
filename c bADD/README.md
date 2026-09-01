# Remote Notification Service

An independent Express service that receives authenticated login-success events and emails the user and an internal administrator through Gmail SMTP.

```mermaid
flowchart LR
    A[User] --> B[Login System]
    B -->|POST login-success| C[Notification Service]
    C --> D[Gmail SMTP]
    D --> E[User email]
    D --> F[Admin email]
```

## Setup

1. Install Node.js 18 or newer and run `npm install`. For a quick shareable dependency list, see `requirements.txt`; npm installs from `package.json`.
2. Copy `.env.example` to `.env` and fill in each value.
3. For Gmail, enable two-step verification and create a [Google App Password](https://support.google.com/accounts/answer/185833). Put that app password in `SMTP_PASS`.
4. Start the service with `npm run dev` (or `npm start`).

The service starts at `http://localhost:3000`; `GET /health` checks that it is running.


```powershell
Copy-Item .env.example .env
npm install
```

`node_modules/` and `.tools/` are also ignored because collaborators can generate them locally.

## Login-success API

`POST /notifications/login-success`

Required header:

```text
Authorization: Bearer <NOTIFICATION_API_KEY>
Content-Type: application/json
```

Example body:

```json
{
  "userName": "Rahul",
  "userEmail": "rahul@example.com",
  "loginTime": "2026-09-01 17:30",
  "device": "Chrome on Windows"
}
```

Example request in PowerShell:

```powershell
$headers = @{ Authorization = 'Bearer replace-with-a-long-random-secret' }
$body = @{ userName = 'Rahul'; userEmail = 'rahul@example.com'; loginTime = '2026-09-01 17:30'; device = 'Chrome on Windows' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://localhost:3000/notifications/login-success' -Headers $headers -ContentType 'application/json' -Body $body
```

On success it returns `202 Accepted`. Bad JSON or fields return `400`; an invalid or absent service secret returns `401`; an SMTP failure returns `502`. Successful and failed email delivery attempts are logged to the terminal.

## Test

Run `npm test`. The tests use a fake mailer, so no Gmail credentials or network connection are needed.

## Extending it

Add new protected endpoints such as `/notifications/password-reset` or `/notifications/registration`, then add their templates beside `createLoginEmails` in `src/mailer.js`. Keeping this service separate lets the login and other applications emit notification events without owning SMTP configuration or email templates.
