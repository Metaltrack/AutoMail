"""Sign-up, email confirmation, login by email and password reset.

Account emails are captured instead of sent: `mails` holds what would have been mailed.
"""
import re

import pytest

import AutoMailAPI
import account_mail
import auth

PASSWORD = "correct-horse-1"


@pytest.fixture(autouse=True)
def fresh_limits():
    auth._hits.clear()          # the rate limiter is per address, and every test client has the same one


@pytest.fixture
def mails(monkeypatch):
    sent = []
    monkeypatch.setattr(account_mail, "deliver",
                        lambda doctor, to, subject, intro, button, link, outro: sent.append(
                            {"to": to, "subject": subject, "link": link}))
    return sent


def token_from(mail) -> str:
    return re.search(r"#/(?:verify|reset)/([\w-]+)$", mail["link"]).group(1)


def signup(client, name="ravi", email="ravi@example.com", password=PASSWORD):
    return client.post("/api/signup", json={"username": name, "email": email, "password": password})


def login(client, who, password=PASSWORD):
    return client.post("/api/login", json={"username": who, "password": password})


def test_signup_needs_email_confirmation_before_login(client, mails):
    assert signup(client).status_code == 200
    assert len(mails) == 1 and mails[0]["to"] == "ravi@example.com"
    assert "/#/verify/" in mails[0]["link"]

    blocked = login(client, "ravi")
    assert blocked.status_code == 403 and "verify" in blocked.json()["detail"].lower()

    assert client.post("/api/verify-email", json={"token": token_from(mails[0])}).status_code == 200
    assert login(client, "ravi").status_code == 200
    assert login(client, "RAVI@example.com").status_code == 200        # the email works as a username too


def test_wrong_password_does_not_reveal_unverified_state(client, mails):
    signup(client, "meera", "meera@example.com")
    assert login(client, "meera", "wrong-password-1").status_code == 401


def test_confirmation_link_works_once(client, mails):
    signup(client, "once", "once@example.com")
    token = token_from(mails[0])
    assert client.post("/api/verify-email", json={"token": token}).status_code == 200
    assert client.post("/api/verify-email", json={"token": token}).status_code == 400
    assert client.post("/api/verify-email", json={"token": "x" * 43}).status_code == 400


def test_resend_replaces_the_old_link(client, mails):
    signup(client, "resend", "resend@example.com")
    old = token_from(mails[0])
    assert client.post("/api/resend-verification", json={"identifier": "resend@example.com"}).status_code == 200
    assert len(mails) == 2
    assert client.post("/api/verify-email", json={"token": old}).status_code == 400
    assert client.post("/api/verify-email", json={"token": token_from(mails[1])}).status_code == 200


def test_resend_for_unknown_account_looks_the_same_but_sends_nothing(client, mails):
    r = client.post("/api/resend-verification", json={"identifier": "nobody@example.com"})
    assert r.status_code == 200 and r.json()["ok"] and not mails


def test_username_and_email_must_be_unique(client, mails):
    signup(client, "taken", "taken@example.com")
    client.post("/api/verify-email", json={"token": token_from(mails[0])})
    assert signup(client, "taken", "other@example.com").status_code == 409
    assert signup(client, "other", "TAKEN@example.com").status_code == 409


def test_unverified_signup_does_not_block_the_real_owner(client, mails):
    signup(client, "squatter", "owner@example.com", "squatter-pass-1")       # someone else typed this address
    signup(client, "realowner", "owner@example.com")
    assert len(mails) == 2
    client.post("/api/verify-email", json={"token": token_from(mails[1])})
    assert login(client, "realowner").status_code == 200
    assert login(client, "squatter", "squatter-pass-1").status_code == 401


def test_weak_or_invalid_input_is_rejected(client, mails):
    assert signup(client, password="short").status_code == 422
    assert signup(client, email="not-an-email").status_code == 422
    assert signup(client, name="a b").status_code == 422
    assert not mails


def test_signup_can_be_closed_or_limited_to_a_domain(client, mails, monkeypatch):
    monkeypatch.setattr(AutoMailAPI, "ALLOW_SIGNUP", False)
    assert signup(client, "closed", "closed@example.com").status_code == 403
    monkeypatch.setattr(AutoMailAPI, "ALLOW_SIGNUP", True)
    monkeypatch.setattr(AutoMailAPI, "ALLOWED_EMAIL_DOMAINS", ["college.edu"])
    assert signup(client, "outsider", "outsider@gmail.com").status_code == 403
    assert signup(client, "student", "student@college.edu").status_code == 200


def test_signup_is_rate_limited(client, mails):
    codes = [signup(client, f"user{i}", f"user{i}@example.com").status_code for i in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_admin_email_becomes_admin_after_confirming(client, mails, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    signup(client, "boss", "boss@example.com")
    client.post("/api/verify-email", json={"token": token_from(mails[0])})
    token = login(client, "boss").json()["token"]
    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "admin" and me["email"] == "boss@example.com"
    # an ordinary address stays a sender
    signup(client, "worker", "worker@example.com")
    client.post("/api/verify-email", json={"token": token_from(mails[1])})
    assert login(client, "worker").json()["user"]["role"] == "sender"


def test_password_reset(client, mails):
    signup(client, "forgetful", "forgetful@example.com")
    client.post("/api/verify-email", json={"token": token_from(mails[0])})
    session = login(client, "forgetful").json()["token"]
    mails.clear()

    # unknown address: same answer, no mail
    assert client.post("/api/forgot-password", json={"email": "ghost@example.com"}).json()["ok"]
    assert not mails

    assert client.post("/api/forgot-password", json={"email": "forgetful@example.com"}).status_code == 200
    assert len(mails) == 1 and "/#/reset/" in mails[0]["link"]
    token = token_from(mails[0])

    assert client.post("/api/reset-password", json={"token": token, "password": "short"}).status_code == 422
    assert client.post("/api/reset-password", json={"token": token, "password": "brand-new-pass-1"}).status_code == 200

    assert login(client, "forgetful").status_code == 401                          # old password is dead
    assert login(client, "forgetful", "brand-new-pass-1").status_code == 200
    assert client.get("/api/me", headers={"Authorization": f"Bearer {session}"}).status_code == 401   # signed out everywhere
    assert client.post("/api/reset-password", json={"token": token, "password": "another-pass-1"}).status_code == 400


def test_unconfirmed_account_cannot_reset_password(client, mails):
    signup(client, "pending", "pending@example.com")
    mails.clear()
    client.post("/api/forgot-password", json={"email": "pending@example.com"})
    assert not mails


def test_account_mail_has_text_and_html_parts_with_the_link():
    msg = account_mail._render(AutoMailAPI.doctor, "a@example.com", "Hi", "Intro <b>", "Go", "http://x/#/verify/abc", "Bye")
    assert msg["To"] == "a@example.com" and msg.get_content_type() == "multipart/alternative"
    text = msg.get_body(("plain",)).get_content()
    page = msg.get_body(("html",)).get_content()
    assert "http://x/#/verify/abc" in text and 'href="http://x/#/verify/abc"' in page
    assert "Intro &lt;b&gt;" in page                       # user-supplied text is escaped in the HTML part


def test_env_file_comments_and_quotes(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# full-line comment\nA_NUM=450          # trailing comment\nA_PASS=xxxx xxxx xxxx xxxx\n'
                 'A_QUOTED="has # hash"\nA_EMPTY=                     # nothing here\n', encoding="utf-8")
    for k in ("A_NUM", "A_PASS", "A_QUOTED", "A_EMPTY"):
        monkeypatch.delenv(k, raising=False)
    AutoMailAPI.load_env_file(f)
    import os
    assert (os.environ["A_NUM"], os.environ["A_PASS"], os.environ["A_QUOTED"], os.environ["A_EMPTY"]) == \
           ("450", "xxxx xxxx xxxx xxxx", "has # hash", "")
    for k in ("A_NUM", "A_PASS", "A_QUOTED", "A_EMPTY"):
        os.environ.pop(k, None)


def test_public_config(client):
    cfg = client.get("/api/config").json()
    assert cfg["signup"] is True and cfg["password_min"] == 8
