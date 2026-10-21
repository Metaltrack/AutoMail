import os
import sqlite3

from datetime import (
    datetime,
    timezone
)

from fastapi import (
    FastAPI,
    HTTPException,
    Response
)

from fastapi.middleware.cors import (
    CORSMiddleware
)

from fastapi.responses import (
    HTMLResponse,
    JSONResponse
)

import uvicorn

import Worker


# ============================================================
# CONFIGURATION
# ============================================================

MAIL_SENDER = os.getenv(
    "MAIL_SENDER",
    "drmailsender@gmail.com"
)

MAIL_APP_PASSWORD = os.getenv(
    "MAIL_APP_PASSWORD",
    ""
)

DB_FILE = os.getenv(
    "MAIL_HISTORY_DB",
    "mail_history.db"
)


APP_STARTED_AT = datetime.now(
    timezone.utc
)


# ============================================================
# MAIL WORKER
# ============================================================

doctor = Worker.DrMail(
    MAIL_SENDER,
    MAIL_APP_PASSWORD
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="DrMail Service",
    description=(
        "Dockerized email delivery microservice "
        "with bulk mail, history and monitoring."
    ),
    version="2.0.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(

    CORSMiddleware,

    allow_origins=[
        "*"
    ],

    allow_credentials=False,

    allow_methods=[
        "*"
    ],

    allow_headers=[
        "*"
    ],
)


# ============================================================
# UTILITY
# ============================================================

def now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def get_uptime():

    now = datetime.now(
        timezone.utc
    )

    return int(
        (
            now
            -
            APP_STARTED_AT
        ).total_seconds()
    )


# ============================================================
# DATABASE
# ============================================================

def get_database():

    conn = sqlite3.connect(
        DB_FILE,
        timeout=10
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_database():

    conn = get_database()

    cursor = conn.cursor()


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mail_history
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            sender TEXT NOT NULL,

            recipients TEXT NOT NULL,

            subject TEXT,

            message TEXT,

            status TEXT NOT NULL,

            error TEXT,

            sent_at TEXT NOT NULL
        )
    """)


    #
    # Migration for databases created by
    # the previous version of the project.
    #

    cursor.execute(
        "PRAGMA table_info(mail_history)"
    )

    columns = [
        row["name"]
        for row in cursor.fetchall()
    ]


    if "error" not in columns:

        cursor.execute("""
            ALTER TABLE mail_history
            ADD COLUMN error TEXT
        """)


    conn.commit()

    conn.close()


def add_mail_history(
    sender,
    recipients,
    subject,
    message,
    status,
    error=None
):

    if isinstance(
        recipients,
        list
    ):

        recipients = ",".join(
            str(x)
            for x in recipients
        )


    conn = get_database()

    cursor = conn.cursor()


    cursor.execute("""
        INSERT INTO mail_history
        (
            sender,
            recipients,
            subject,
            message,
            status,
            error,
            sent_at
        )

        VALUES
        (
            ?, ?, ?, ?, ?, ?, ?
        )
    """,
    (
        sender,
        recipients,
        subject,
        message,
        status,
        error,
        now_iso()
    ))


    conn.commit()

    conn.close()


def check_database():

    try:

        conn = get_database()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1"
        )

        cursor.fetchone()

        conn.close()


        return {
            "healthy": True
        }


    except Exception as err:

        return {
            "healthy": False,
            "error": str(err)
        }


# Initialize database

init_database()


# ============================================================
# HEALTH ENDPOINT
# ============================================================

@app.get("/health")
def health():

    database = check_database()


    healthy = database[
        "healthy"
    ]


    payload = {

        "status":
            "healthy"
            if healthy
            else
            "degraded",

        "service":
            "DrMail",

        "version":
            "2.0.0",

        "uptime_seconds":
            get_uptime(),

        "database":
            database,

        "timestamp":
            now_iso()
    }


    if not healthy:

        return JSONResponse(
            status_code=503,
            content=payload
        )


    return payload


# ============================================================
# DATABASE HEALTH
# ============================================================

@app.get("/health/database")
def database_health():

    result = check_database()


    if not result["healthy"]:

        return JSONResponse(

            status_code=503,

            content={
                "status":
                    "unhealthy",

                "database":
                    "sqlite",

                "error":
                    result.get(
                        "error"
                    )
            }
        )


    return {

        "status":
            "healthy",

        "database":
            "sqlite",

        "file":
            DB_FILE
    }


# ============================================================
# SMTP HEALTH
# ============================================================

@app.get("/health/smtp")
def smtp_health():

    result = doctor.CheckConnection()


    if not result[
        "reachable"
    ]:

        return JSONResponse(

            status_code=503,

            content={

                "status":
                    "unreachable",

                "provider":
                    "smtp.gmail.com",

                "error":
                    result.get(
                        "error"
                    )
            }
        )


    return {

        "status":
            "reachable",

        "provider":
            "smtp.gmail.com",

        "smtp_status":
            result.get(
                "status_code"
            )
    }


# ============================================================
# READINESS
# ============================================================

@app.get("/ready")
def readiness():

    database = check_database()

    credentials_configured = bool(
        MAIL_SENDER
        and
        MAIL_APP_PASSWORD
    )


    ready = (

        database["healthy"]

        and

        credentials_configured
    )


    result = {

        "ready":
            ready,

        "database":
            database["healthy"],

        "mail_credentials":
            credentials_configured,

        "timestamp":
            now_iso()
    }


    if not ready:

        return JSONResponse(

            status_code=503,

            content=result
        )


    return result


# ============================================================
# APPLICATION INFO
# ============================================================

@app.get("/info")
def application_info():

    return {

        "name":
            "DrMail",

        "version":
            "2.0.0",

        "description":
            "Email delivery microservice",

        "sender":
            MAIL_SENDER,

        "features": [

            "Single email",

            "Bulk email",

            "SQLite email history",

            "REST API",

            "Web dashboard",

            "SMTP monitoring",

            "Database monitoring",

            "Readiness checks",

            "Operational statistics"
        ],

        "endpoints": {

            "dashboard":
                "/",

            "swagger":
                "/docs",

            "health":
                "/health",

            "smtp_health":
                "/health/smtp",

            "database_health":
                "/health/database",

            "readiness":
                "/ready",

            "stats":
                "/stats",

            "history":
                "/history"
        }
    }


# ============================================================
# STATISTICS
# ============================================================

@app.get("/stats")
def stats():

    conn = get_database()

    cursor = conn.cursor()


    cursor.execute("""
        SELECT COUNT(*)
        FROM mail_history
    """)

    total = cursor.fetchone()[0]


    cursor.execute("""
        SELECT COUNT(*)
        FROM mail_history
        WHERE status = 'success'
    """)

    successful = cursor.fetchone()[0]


    cursor.execute("""
        SELECT COUNT(*)
        FROM mail_history
        WHERE status = 'failed'
    """)

    failed = cursor.fetchone()[0]


    conn.close()


    success_rate = 0


    if total > 0:

        success_rate = round(
            successful
            /
            total
            *
            100,
            2
        )


    return {

        "total":
            total,

        "successful":
            successful,

        "failed":
            failed,

        "success_rate":
            success_rate,

        "uptime_seconds":
            get_uptime()
    }


# ============================================================
# SEND SINGLE EMAIL
# ============================================================

@app.post("/send_mail")
def send_mail(data: dict):

    required_fields = [

        "to",

        "sub",

        "msg_content"
    ]


    missing = [

        field

        for field in required_fields

        if not data.get(
            field
        )
    ]


    if missing:

        raise HTTPException(

            status_code=400,

            detail=
                "Missing fields: "
                +
                ", ".join(
                    missing
                )
        )


    sender = MAIL_SENDER

    recipient = str(
        data["to"]
    ).strip()

    subject = str(
        data["sub"]
    )

    message = str(
        data["msg_content"]
    )


    try:

        doctor.SendMail(

            sender,

            recipient,

            subject,

            message
        )


        add_mail_history(

            sender,

            recipient,

            subject,

            message,

            "success"
        )


        return {

            "status":
                "success",

            "recipient":
                recipient
        }


    except Exception as err:

        add_mail_history(

            sender,

            recipient,

            subject,

            message,

            "failed",

            str(err)
        )


        raise HTTPException(

            status_code=502,

            detail=
                f"Mail provider error: {err}"
        )


# ============================================================
# SEND BULK EMAIL
# ============================================================

@app.post("/send_multiple_mail")
def send_multiple_mail(data: dict):

    recipients = data.get(
        "to"
    )


    if not isinstance(
        recipients,
        list
    ):

        raise HTTPException(

            status_code=400,

            detail=(
                "'to' must be a list "
                "of email addresses."
            )
        )


    recipients = [

        str(address).strip()

        for address in recipients

        if str(address).strip()
    ]


    if len(recipients) == 0:

        raise HTTPException(

            status_code=400,

            detail=(
                "At least one recipient "
                "is required."
            )
        )


    subject = str(
        data.get(
            "sub",
            ""
        )
    )


    message = str(
        data.get(
            "msg_content",
            ""
        )
    )


    if not subject:

        raise HTTPException(

            status_code=400,

            detail=
                "Subject cannot be empty."
        )


    if not message:

        raise HTTPException(

            status_code=400,

            detail=
                "Message cannot be empty."
        )


    sender = MAIL_SENDER


    try:

        sent_count = (
            doctor
            .SendMultipleMailAPI(

                sender,

                recipients,

                subject,

                message
            )
        )


        add_mail_history(

            sender,

            recipients,

            subject,

            message,

            "success"
        )


        return {

            "status":
                "success",

            "recipients":
                sent_count
        }


    except Exception as err:

        add_mail_history(

            sender,

            recipients,

            subject,

            message,

            "failed",

            str(err)
        )


        raise HTTPException(

            status_code=502,

            detail=
                f"Mail provider error: {err}"
        )


# ============================================================
# GET HISTORY
# ============================================================

@app.get("/history")
def get_history(
    limit: int = 50
):

    if limit < 1:
        limit = 1


    if limit > 200:
        limit = 200


    conn = get_database()

    cursor = conn.cursor()


    cursor.execute("""
        SELECT
            id,
            sender,
            recipients,
            subject,
            message,
            status,
            error,
            sent_at

        FROM mail_history

        ORDER BY id DESC

        LIMIT ?
    """,
    (
        limit,
    ))


    rows = cursor.fetchall()

    conn.close()


    return {

        "history": [

            dict(row)

            for row in rows
        ]
    }


# ============================================================
# GET ONE HISTORY ENTRY
# ============================================================

@app.get("/history/{mail_id}")
def get_history_entry(
    mail_id: int
):

    conn = get_database()

    cursor = conn.cursor()


    cursor.execute("""
        SELECT *
        FROM mail_history
        WHERE id = ?
    """,
    (
        mail_id,
    ))


    row = cursor.fetchone()

    conn.close()


    if row is None:

        raise HTTPException(

            status_code=404,

            detail=
                "History entry not found."
        )


    return dict(
        row
    )


# ============================================================
# DELETE HISTORY ENTRY
# ============================================================

@app.delete("/history/{mail_id}")
def delete_history(
    mail_id: int
):

    conn = get_database()

    cursor = conn.cursor()


    cursor.execute("""
        DELETE FROM mail_history
        WHERE id = ?
    """,
    (
        mail_id,
    ))


    deleted = (
        cursor.rowcount
    )


    conn.commit()

    conn.close()


    if deleted == 0:

        raise HTTPException(

            status_code=404,

            detail=
                "History entry not found."
        )


    return {

        "status":
            "success",

        "deleted":
            mail_id
    }


# ============================================================
# CLEAR HISTORY
# ============================================================

@app.delete("/history")
def clear_history():

    conn = get_database()

    cursor = conn.cursor()


    cursor.execute(
        "DELETE FROM mail_history"
    )


    deleted = (
        cursor.rowcount
    )


    conn.commit()

    conn.close()


    return {

        "status":
            "success",

        "deleted":
            deleted
    }


# ============================================================
# FAVICON
# ============================================================

@app.get("/favicon.ico")
def favicon():

    return Response(
        status_code=204
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def interface():

    return """
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>DrMail Dashboard</title>


<style>

* {
    box-sizing: border-box;
}

:root {

    --bg:
        #080c14;

    --panel:
        #101722;

    --panel-2:
        #0c121d;

    --border:
        #273249;

    --border-light:
        #34415d;

    --text:
        #edf1f8;

    --muted:
        #8995aa;

    --primary:
        #627cff;

    --primary-2:
        #8e62ff;

    --success:
        #4fd68c;

    --danger:
        #ff6e7d;

    --warning:
        #f5bf5b;
}


body {

    margin: 0;

    min-height: 100vh;

    font-family:
        "Segoe UI",
        Arial,
        sans-serif;

    color:
        var(--text);

    background:

        radial-gradient(
            circle at 15% 0%,
            #1a284b 0,
            transparent 32%
        ),

        radial-gradient(
            circle at 85% 20%,
            #251c43 0,
            transparent 27%
        ),

        var(--bg);
}


button,
input,
textarea {

    font:
        inherit;
}


/* =========================================================
   HEADER
========================================================= */

header {

    height: 72px;

    padding:
        0 34px;

    display:
        flex;

    align-items:
        center;

    justify-content:
        space-between;

    position:
        sticky;

    top:
        0;

    z-index:
        20;

    border-bottom:
        1px solid
        var(--border);

    background:
        rgba(
            8,
            12,
            20,
            .84
        );

    backdrop-filter:
        blur(18px);
}


.brand {

    display:
        flex;

    align-items:
        center;

    gap:
        13px;
}


.logo {

    width:
        40px;

    height:
        40px;

    border-radius:
        11px;

    display:
        grid;

    place-items:
        center;

    font-weight:
        800;

    background:
        linear-gradient(
            135deg,
            var(--primary),
            var(--primary-2)
        );

    box-shadow:
        0 8px 28px
        rgba(
            98,
            124,
            255,
            .24
        );
}


.brand-name {

    font-size:
        17px;

    font-weight:
        750;
}


.brand-subtitle {

    margin-top:
        2px;

    color:
        var(--muted);

    font-size:
        11px;
}


.header-right {

    display:
        flex;

    align-items:
        center;

    gap:
        18px;
}


.health {

    display:
        flex;

    align-items:
        center;

    gap:
        8px;

    color:
        var(--muted);

    font-size:
        12px;
}


.health-dot {

    width:
        9px;

    height:
        9px;

    border-radius:
        50%;

    background:
        var(--warning);
}


.health-dot.good {

    background:
        var(--success);

    box-shadow:
        0 0 12px
        var(--success);
}


.health-dot.bad {

    background:
        var(--danger);

    box-shadow:
        0 0 12px
        var(--danger);
}


.nav-link {

    color:
        #b8c2d5;

    text-decoration:
        none;

    font-size:
        12px;

    padding:
        8px 11px;

    border:
        1px solid
        var(--border);

    border-radius:
        8px;

    transition:
        .15s;
}


.nav-link:hover {

    color:
        white;

    border-color:
        var(--border-light);

    background:
        #151e2c;
}


/* =========================================================
   PAGE
========================================================= */

main {

    max-width:
        1400px;

    margin:
        0 auto;

    padding:
        30px;
}


/* =========================================================
   STAT CARDS
========================================================= */

.stats {

    display:
        grid;

    grid-template-columns:
        repeat(
            4,
            1fr
        );

    gap:
        14px;

    margin-bottom:
        24px;
}


.stat {

    padding:
        18px;

    border:
        1px solid
        var(--border);

    border-radius:
        14px;

    background:
        linear-gradient(
            145deg,
            rgba(
                19,
                27,
                42,
                .95
            ),
            rgba(
                12,
                18,
                29,
                .95
            )
        );
}


.stat-label {

    color:
        var(--muted);

    font-size:
        11px;

    letter-spacing:
        .6px;
}


.stat-value {

    margin-top:
        8px;

    font-size:
        28px;

    font-weight:
        780;
}


.stat-small {

    margin-top:
        4px;

    color:
        #6f7b90;

    font-size:
        11px;
}


/* =========================================================
   MAIN GRID
========================================================= */

.layout {

    display:
        grid;

    grid-template-columns:
        minmax(
            0,
            1.35fr
        )
        minmax(
            330px,
            .85fr
        );

    gap:
        22px;
}


/* =========================================================
   CARDS
========================================================= */

.card {

    border:
        1px solid
        var(--border);

    border-radius:
        16px;

    background:
        rgba(
            15,
            22,
            34,
            .94
        );

    box-shadow:
        0 20px 55px
        rgba(
            0,
            0,
            0,
            .25
        );

    overflow:
        hidden;
}


.card-header {

    padding:
        20px 22px;

    border-bottom:
        1px solid
        var(--border);
}


.card-title {

    font-size:
        17px;

    font-weight:
        720;
}


.card-subtitle {

    margin-top:
        4px;

    color:
        var(--muted);

    font-size:
        12px;
}


.card-body {

    padding:
        22px;
}


/* =========================================================
   FORM
========================================================= */

.form-row {

    display:
        grid;

    grid-template-columns:
        1fr 1fr;

    gap:
        14px;
}


label {

    display:
        block;

    margin-bottom:
        7px;

    color:
        #abb5c8;

    font-size:
        12px;

    font-weight:
        600;
}


input,
textarea {

    width:
        100%;

    margin-bottom:
        17px;

    padding:
        12px 13px;

    color:
        var(--text);

    background:
        var(--panel-2);

    border:
        1px solid
        var(--border);

    border-radius:
        9px;

    outline:
        none;

    transition:
        .15s;
}


input:focus,
textarea:focus {

    border-color:
        var(--primary);

    box-shadow:
        0 0 0 3px
        rgba(
            98,
            124,
            255,
            .12
        );
}


input[readonly] {

    color:
        #98a5ba;

    cursor:
        default;
}


textarea {

    min-height:
        130px;

    resize:
        vertical;
}


#message {

    min-height:
        185px;
}


/* =========================================================
   BUTTONS
========================================================= */

.actions {

    display:
        flex;

    align-items:
        center;

    gap:
        10px;
}


button {

    padding:
        11px 17px;

    border:
        0;

    border-radius:
        9px;

    cursor:
        pointer;

    font-weight:
        650;

    transition:
        .15s;
}


button:hover {

    transform:
        translateY(-1px);
}


button:active {

    transform:
        translateY(0);
}


.primary {

    color:
        white;

    background:
        linear-gradient(
            135deg,
            var(--primary),
            var(--primary-2)
        );
}


.secondary {

    color:
        #ccd4e1;

    background:
        #202a3c;

    border:
        1px solid
        #303d56;
}


.danger-button {

    color:
        #ffabb3;

    background:
        rgba(
            255,
            93,
            110,
            .09
        );

    border:
        1px solid
        rgba(
            255,
            93,
            110,
            .22
        );
}


/* =========================================================
   SEND STATUS
========================================================= */

#send-status {

    display:
        none;

    margin-top:
        16px;

    padding:
        12px 14px;

    border-radius:
        9px;

    font-size:
        12px;
}


#send-status.success-message {

    display:
        block;

    color:
        #87edb3;

    background:
        rgba(
            79,
            214,
            140,
            .09
        );

    border:
        1px solid
        rgba(
            79,
            214,
            140,
            .2
        );
}


#send-status.error-message {

    display:
        block;

    color:
        #ff9ba5;

    background:
        rgba(
            255,
            110,
            125,
            .09
        );

    border:
        1px solid
        rgba(
            255,
            110,
            125,
            .2
        );
}


/* =========================================================
   HISTORY
========================================================= */

.history-toolbar {

    display:
        flex;

    justify-content:
        space-between;

    gap:
        8px;

    padding:
        14px 18px;

    border-bottom:
        1px solid
        var(--border);
}


.history-toolbar button {

    padding:
        8px 11px;

    font-size:
        11px;
}


.history {

    max-height:
        620px;

    overflow-y:
        auto;

    padding:
        14px;
}


.history-empty {

    padding:
        35px 20px;

    text-align:
        center;

    color:
        var(--muted);

    font-size:
        12px;
}


.history-item {

    position:
        relative;

    padding:
        14px;

    margin-bottom:
        10px;

    background:
        var(--panel-2);

    border:
        1px solid
        var(--border);

    border-radius:
        11px;
}


.history-top {

    display:
        flex;

    align-items:
        flex-start;

    justify-content:
        space-between;

    gap:
        12px;
}


.history-subject {

    font-size:
        13px;

    font-weight:
        650;
}


.history-recipient {

    margin-top:
        6px;

    color:
        #99a5b9;

    font-size:
        11px;

    word-break:
        break-word;
}


.history-bottom {

    margin-top:
        10px;

    display:
        flex;

    justify-content:
        space-between;

    color:
        #667289;

    font-size:
        10px;
}


.badge {

    padding:
        3px 7px;

    border-radius:
        20px;

    font-size:
        9px;

    font-weight:
        750;

    text-transform:
        uppercase;
}


.badge.success {

    color:
        #71e8a5;

    background:
        rgba(
            79,
            214,
            140,
            .1
        );
}


.badge.failed {

    color:
        #ff8f9b;

    background:
        rgba(
            255,
            110,
            125,
            .1
        );
}


/* =========================================================
   RESPONSIVE
========================================================= */

@media (
    max-width:
    950px
) {

    .layout {

        grid-template-columns:
            1fr;
    }


    .stats {

        grid-template-columns:
            1fr 1fr;
    }

}


@media (
    max-width:
    600px
) {

    header {

        padding:
            0 16px;
    }


    main {

        padding:
            18px;
    }


    .stats {

        grid-template-columns:
            1fr;
    }


    .form-row {

        grid-template-columns:
            1fr;
    }


    .header-right
    .nav-link {

        display:
            none;
    }

}

</style>

</head>



<body>


<header>

    <div class="brand">

        <div class="logo">
            D
        </div>


        <div>

            <div class="brand-name">
                DrMail
            </div>

            <div class="brand-subtitle">
                Mail Delivery Microservice
            </div>

        </div>

    </div>


    <div class="header-right">


        <div class="health">

            <div
                id="service-dot"
                class="health-dot"
            ></div>

            <span id="service-status">
                Checking...
            </span>

        </div>


        <a
            class="nav-link"
            href="/docs"
            target="_blank"
        >
            API Docs
        </a>


        <a
            class="nav-link"
            href="/health"
            target="_blank"
        >
            Health
        </a>

    </div>

</header>



<main>


<div class="stats">


    <div class="stat">

        <div class="stat-label">
            TOTAL EMAIL JOBS
        </div>

        <div
            class="stat-value"
            id="stat-total"
        >
            0
        </div>

        <div class="stat-small">
            Recorded history
        </div>

    </div>


    <div class="stat">

        <div class="stat-label">
            SUCCESSFUL
        </div>

        <div
            class="stat-value"
            id="stat-success"
        >
            0
        </div>

        <div
            class="stat-small"
            id="stat-rate"
        >
            0% success rate
        </div>

    </div>


    <div class="stat">

        <div class="stat-label">
            FAILED
        </div>

        <div
            class="stat-value"
            id="stat-failed"
        >
            0
        </div>

        <div class="stat-small">
            Failed mail jobs
        </div>

    </div>


    <div class="stat">

        <div class="stat-label">
            SMTP PROVIDER
        </div>

        <div
            class="stat-value"
            id="smtp-status"
            style="font-size:20px"
        >
            Checking
        </div>

        <div class="stat-small">
            smtp.gmail.com
        </div>

    </div>


</div>



<div class="layout">


<!-- ======================================================
     MAIL COMPOSER
====================================================== -->

<div class="card">


    <div class="card-header">

        <div class="card-title">
            Compose Email
        </div>

        <div class="card-subtitle">
            Paste recipients directly from Google Sheets,
            Excel or another application.
        </div>

    </div>


    <div class="card-body">


        <div class="form-row">

            <div>

                <label>
                    Sender
                </label>

                <input
                    id="sender"
                    readonly
                    value=""
                >

            </div>


            <div>

                <label>
                    Number of recipients
                </label>

                <input
                    id="recipient-count"
                    readonly
                    value="0"
                >

            </div>

        </div>


        <label>
            Recipients
        </label>

        <textarea
            id="recipients"
            placeholder="Paste email addresses here...

user1@gmail.com
user2@gmail.com
user3@gmail.com"
        ></textarea>


        <label>
            Subject
        </label>

        <input
            id="subject"
            placeholder="Subject"
        >


        <label>
            Message
        </label>

        <textarea
            id="message"
            placeholder="Write your message..."
        ></textarea>


        <div class="actions">

            <button
                class="primary"
                onclick="sendMail()"
                id="send-button"
            >
                Send Email
            </button>


            <button
                class="secondary"
                onclick="clearForm()"
            >
                Clear
            </button>

        </div>


        <div id="send-status"></div>


    </div>

</div>



<!-- ======================================================
     HISTORY
====================================================== -->

<div class="card">


    <div class="card-header">

        <div class="card-title">
            Email History
        </div>

        <div class="card-subtitle">
            Recent delivery attempts
        </div>

    </div>


    <div class="history-toolbar">

        <button
            class="secondary"
            onclick="loadHistory()"
        >
            Refresh
        </button>


        <button
            class="danger-button"
            onclick="clearHistory()"
        >
            Clear History
        </button>

    </div>


    <div
        class="history"
        id="history"
    >
    </div>


</div>


</div>


</main>



<script>


// =========================================================
// HTML ESCAPE
// =========================================================

function escapeHtml(value) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        value ?? "";

    return div.innerHTML;
}


// =========================================================
// RECIPIENT PARSER
// =========================================================

function getRecipients() {

    const text =
        document
        .getElementById(
            "recipients"
        )
        .value;


    return text

        .split(/[\\n,;]+/)

        .map(
            address =>
                address.trim()
        )

        .filter(
            address =>
                address.length > 0
        );
}


// =========================================================
// RECIPIENT COUNTER
// =========================================================

document
.getElementById(
    "recipients"
)
.addEventListener(
    "input",
    function() {

        document
        .getElementById(
            "recipient-count"
        )
        .value =
            getRecipients()
            .length;
    }
);


// =========================================================
// SEND MAIL
// =========================================================

async function sendMail() {

    const recipients =
        getRecipients();


    const subject =
        document
        .getElementById(
            "subject"
        )
        .value
        .trim();


    const message =
        document
        .getElementById(
            "message"
        )
        .value
        .trim();


    if (
        recipients.length === 0
    ) {

        showStatus(
            "Enter at least one recipient.",
            false
        );

        return;
    }


    if (!subject) {

        showStatus(
            "Enter an email subject.",
            false
        );

        return;
    }


    if (!message) {

        showStatus(
            "Enter an email message.",
            false
        );

        return;
    }


    const button =
        document
        .getElementById(
            "send-button"
        );


    button.disabled =
        true;

    button.innerText =
        "Sending...";


    showStatus(
        "Connecting to mail provider...",
        true
    );


    try {


        const response =
            await fetch(

                "/send_multiple_mail",

                {

                    method:
                        "POST",

                    headers: {

                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            to:
                                recipients,

                            sub:
                                subject,

                            msg_content:
                                message
                        })
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(

                data.detail

                ||

                "Mail request failed."
            );
        }


        showStatus(

            "Successfully sent to "

            +

            data.recipients

            +

            " recipient(s).",

            true
        );


        await loadHistory();

        await loadStats();


    }

    catch(error) {


        showStatus(

            error.message,

            false
        );


        await loadHistory();

        await loadStats();

    }

    finally {


        button.disabled =
            false;

        button.innerText =
            "Send Email";

    }

}


// =========================================================
// STATUS MESSAGE
// =========================================================

function showStatus(
    message,
    success
) {

    const element =
        document
        .getElementById(
            "send-status"
        );


    element.textContent =
        message;


    element.className =
        success

        ?

        "success-message"

        :

        "error-message";
}


// =========================================================
// HISTORY
// =========================================================

async function loadHistory() {

    const container =
        document
        .getElementById(
            "history"
        );


    try {


        const response =
            await fetch(
                "/history?limit=30"
            );


        const data =
            await response.json();


        container.innerHTML =
            "";


        if (
            data.history.length === 0
        ) {

            container.innerHTML = `

                <div class="history-empty">

                    No email history yet.

                </div>
            `;

            return;
        }


        data.history.forEach(

            mail => {


                const item =
                    document
                    .createElement(
                        "div"
                    );


                item.className =
                    "history-item";


                item.innerHTML = `

                    <div class="history-top">

                        <div>

                            <div class="history-subject">

                                ${
                                    escapeHtml(
                                        mail.subject
                                        ||
                                        "(No Subject)"
                                    )
                                }

                            </div>


                            <div class="history-recipient">

                                To:

                                ${
                                    escapeHtml(
                                        mail.recipients
                                    )
                                }

                            </div>

                        </div>


                        <span
                            class="badge ${
                                mail.status === "success"
                                ?
                                "success"
                                :
                                "failed"
                            }"
                        >

                            ${
                                escapeHtml(
                                    mail.status
                                )
                            }

                        </span>

                    </div>


                    <div class="history-bottom">

                        <span>

                            ID #${mail.id}

                        </span>


                        <span>

                            ${
                                formatDate(
                                    mail.sent_at
                                )
                            }

                        </span>

                    </div>
                `;


                container
                .appendChild(
                    item
                );

            }
        );


    }

    catch(error) {


        container.innerHTML = `

            <div class="history-empty">

                Unable to load history.

            </div>
        `;

    }

}


// =========================================================
// STATS
// =========================================================

async function loadStats() {

    try {


        const response =
            await fetch(
                "/stats"
            );


        const data =
            await response.json();


        document
        .getElementById(
            "stat-total"
        )
        .textContent =
            data.total;


        document
        .getElementById(
            "stat-success"
        )
        .textContent =
            data.successful;


        document
        .getElementById(
            "stat-failed"
        )
        .textContent =
            data.failed;


        document
        .getElementById(
            "stat-rate"
        )
        .textContent =
            data.success_rate
            +
            "% success rate";


    }

    catch(error) {

        console.error(
            error
        );
    }

}


// =========================================================
// SERVICE HEALTH
// =========================================================

async function loadHealth() {

    const dot =
        document
        .getElementById(
            "service-dot"
        );


    const text =
        document
        .getElementById(
            "service-status"
        );


    try {


        const response =
            await fetch(
                "/health"
            );


        if (!response.ok) {

            throw new Error();
        }


        dot.className =
            "health-dot good";


        text.textContent =
            "Service Online";


    }

    catch(error) {


        dot.className =
            "health-dot bad";


        text.textContent =
            "Service Degraded";

    }

}


// =========================================================
// SMTP HEALTH
// =========================================================

async function loadSMTPHealth() {

    const element =
        document
        .getElementById(
            "smtp-status"
        );


    try {


        const response =
            await fetch(
                "/health/smtp"
            );


        if (!response.ok) {

            element.textContent =
                "Unavailable";

            return;
        }


        element.textContent =
            "Reachable";


    }

    catch(error) {


        element.textContent =
            "Unavailable";

    }

}


// =========================================================
// INFO
// =========================================================

async function loadInfo() {

    try {


        const response =
            await fetch(
                "/info"
            );


        const data =
            await response.json();


        document
        .getElementById(
            "sender"
        )
        .value =
            data.sender;


    }

    catch(error) {

        console.error(
            error
        );
    }

}


// =========================================================
// CLEAR FORM
// =========================================================

function clearForm() {

    document
    .getElementById(
        "recipients"
    )
    .value =
        "";


    document
    .getElementById(
        "subject"
    )
    .value =
        "";


    document
    .getElementById(
        "message"
    )
    .value =
        "";


    document
    .getElementById(
        "recipient-count"
    )
    .value =
        "0";


    document
    .getElementById(
        "send-status"
    )
    .className =
        "";


    document
    .getElementById(
        "send-status"
    )
    .textContent =
        "";
}


// =========================================================
// CLEAR HISTORY
// =========================================================

async function clearHistory() {

    const confirmed =
        confirm(
            "Clear all email history?"
        );


    if (!confirmed) {

        return;
    }


    await fetch(
        "/history",
        {
            method:
                "DELETE"
        }
    );


    await loadHistory();

    await loadStats();
}


// =========================================================
// DATE DISPLAY
// =========================================================

function formatDate(value) {

    try {

        return new Date(
            value
        )
        .toLocaleString();

    }

    catch {

        return value;
    }

}


// =========================================================
// INITIAL LOAD
// =========================================================

async function initialize() {

    await Promise.all([

        loadHealth(),

        loadSMTPHealth(),

        loadStats(),

        loadHistory(),

        loadInfo()
    ]);

}


initialize();


</script>


</body>

</html>
"""


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    uvicorn.run(

        app,

        host="0.0.0.0",

        port=6767
    )