"""Command-line client for the AutoMail service.

Run the API first (python DrPost/AutoMailAPI.py), then run this file.
Sign in with your AutoMail username and password, or set AUTOMAIL_API_KEY to an
app key created under Settings > Connected apps.
AUTOMAIL_URL changes the server address (default http://127.0.0.1:6767).
"""
import getpass
import os
import time
from datetime import datetime, timedelta

import requests

BASE_URL = os.getenv("AUTOMAIL_URL", "http://127.0.0.1:6767").rstrip("/")
HEADERS = {}

BANNER = r"""
    _         _        __  __       _ _
   / \  _   _| |_ ___ |  \/  | __ _(_) |
  / _ \| | | | __/ _ \| |\/| |/ _` | | |
 / ___ \ |_| | || (_) | |  | | (_| | | |
/_/   \_\__,_|\__\___/|_|  |_|\__,_|_|_|
"""

MENU = """
[1] Send a mail now
[2] Schedule a mail
[3] Show recent mail
[4] Exit
"""


class ApiError(Exception):
    pass


def call(method, path, payload=None):
    try:
        resp = requests.request(method, f"{BASE_URL}{path}", json=payload, headers=HEADERS, timeout=30)
    except requests.ConnectionError:
        raise ApiError(f"Could not reach the server at {BASE_URL}. Is AutoMailAPI.py running?")
    except requests.Timeout:
        raise ApiError("The server took too long to answer.")
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if not resp.ok:
        detail = data.get("detail", resp.text)
        if isinstance(detail, list):  # validation errors from FastAPI
            detail = "; ".join(d.get("msg", str(d)).replace("Value error, ", "") for d in detail)
        raise ApiError(f"Error {resp.status_code}: {detail}")
    return data


def ask(prompt, required=True):
    while True:
        value = input(prompt).strip()
        if value or not required:
            return value
        print("  This field is required.")


def ask_message():
    print("Message (use {name} for personalisation; finish with an empty line):")
    lines = []
    while True:
        line = input()
        if line == "" and lines:
            break
        lines.append(line)
    return "\n".join(lines)


def ask_time():
    default = (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    while True:
        raw = input(f"Send at (YYYY-MM-DD HH:MM) [{default:%Y-%m-%d %H:%M}]: ").strip()
        if not raw:
            return default
        try:
            when = datetime.strptime(raw, "%Y-%m-%d %H:%M")
        except ValueError:
            print("  Use the format 2026-11-23 09:00")
            continue
        if when <= datetime.now():
            print("  That time has passed. Pick a later one.")
            continue
        return when


def compose(schedule):
    payload = {
        "to": ask("To (comma separated, or leave empty to use a group): ", required=False),
        "subject": ask("Subject: "),
        "body": ask_message(),
    }
    group = ""
    if not payload["to"]:
        group = ask("Contact group name: ")
        payload["groups"] = [group]
    if schedule:
        payload["send_at"] = ask_time().astimezone().isoformat()
        rep = ask("Repeat? [n]one / [d]aily / [w]eekly: ", required=False).lower()[:1]
        payload["repeat"] = {"d": "daily", "w": "weekly"}.get(rep, "none")

    job = call("POST", "/api/send", payload)
    if job["status"] == "scheduled":
        when = datetime.fromtimestamp(job["scheduled_at"]).strftime("%a %d %b, %H:%M")
        print(f"\n  Scheduled for {when} to {job['recipients']} recipient(s). Job #{job['job_id']}.\n")
        return
    print(f"\n  Queued for {job['recipients']} recipient(s). Watching progress...")
    for _ in range(60):
        time.sleep(1)
        j = call("GET", f"/api/jobs/{job['job_id']}")
        print(f"\r  {j['sent']} sent, {j['failed']} failed, {j['pending']} waiting   ", end="", flush=True)
        if j["status"] not in ("scheduled", "sending"):
            break
    note = " (dry run: nothing was really delivered)" if job.get("dry_run") else ""
    print(f"\n  Status: {j['status']}{note}\n")
    for m in j["messages"]:
        if m["status"] == "failed":
            print(f"    x {m['email']}: {m['last_error']}")


def show_recent():
    jobs = call("GET", "/api/jobs?limit=10")
    if not jobs:
        print("\n  Nothing sent yet.\n")
        return
    print()
    for j in jobs:
        when = datetime.fromtimestamp(j["scheduled_at"]).strftime("%d %b %H:%M")
        print(f"  #{j['id']:<4} {when}  {j['status']:<10} {j['sent']}/{j['total']} sent  {j['subject']}")
    print()


def sign_in():
    key = os.getenv("AUTOMAIL_API_KEY")
    if key:
        HEADERS["X-API-Key"] = key
        print("Using the API key from AUTOMAIL_API_KEY.")
        return
    while True:
        user = ask("Username: ")
        password = getpass.getpass("Password: ")
        try:
            token = call("POST", "/api/login", {"username": user, "password": password})["token"]
            HEADERS["Authorization"] = f"Bearer {token}"
            print(f"Signed in as {user}.")
            return
        except ApiError as err:
            print(f"  {err}")


def main():
    print(BANNER)
    print(f"Server: {BASE_URL}")
    sign_in()
    while True:
        print(MENU)
        choice = input("Choice: ").strip()
        try:
            if choice == "1":
                compose(schedule=False)
            elif choice == "2":
                compose(schedule=True)
            elif choice == "3":
                show_recent()
            elif choice == "4":
                break
            else:
                print("  Please enter 1, 2, 3 or 4.")
        except ApiError as err:
            print(f"\n  {err}\n")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")
