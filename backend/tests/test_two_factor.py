"""The second factor: what it protects, and what it must not break.

A second factor is worth having only if the awkward cases are right, so
those are what these tests are about:

1. **The challenge is not a session.** Half a sign-in presented as a whole
   one would make the second step optional for anyone who noticed.
2. **An enrolment counts only once a code has been checked.** Scanning a QR
   and closing the page must not lock somebody out of their own account.
3. **Recovery codes work where the factor is expected**, because a phone in
   a canal is the situation they exist for — and each works once.
4. **Turning it off needs a code**, or a borrowed session strips the very
   protection it is facing.
5. **The clock is allowed to drift** by one step, which is what an unsynced
   phone looks like.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import auth as auth_route
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.deps import get_current_user, require_admin
from app.core.security import (
    CHALLENGE_CLAIM,
    create_challenge_token,
    hash_password,
)
from app.main import app
from app.models.two_factor import TwoFactorCode, TwoFactorEnrolment
from app.models.user import User
from app.schemas.settings import InstanceSettings
from app.services import two_factor


@pytest.fixture
def db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, username="ada", email="ada@example.com",
                     password_hash=hash_password("old-password"), role="admin"))
    session.add(User(id=2, username="bob", email="bob@example.com",
                     password_hash=hash_password("bobs-password"), role="user"))
    session.commit()
    yield session
    session.close()
    get_settings.cache_clear()


@pytest.fixture
def sent(db, monkeypatch):
    messages: list[dict] = []
    settings = InstanceSettings(
        mail_enabled=True, mail_host="smtp.example.com",
        mail_from="emcargo@example.com")
    monkeypatch.setattr(auth_route, "instance_settings", lambda db: settings)
    monkeypatch.setattr(
        auth_route.mail, "send",
        lambda config, to, subject, body, attachments=None, html=None: messages.append(
            {"to": to, "subject": subject, "body": body}))
    return messages


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(auth_route.limiter, "enabled", False)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def signed_in(client, db):
    """A client acting as ada, for the self-service endpoints."""
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


def code_in(message: dict) -> str:
    for word in message["body"].split():
        if word.isdigit() and len(word) == 6:
            return word
    raise AssertionError(f"no code in: {message['body']}")


# --- TOTP itself ------------------------------------------------------------


def test_totp_matches_the_rfc_test_vector():
    """RFC 6238 appendix B: the secret "12345678901234567890" at
    1970-01-01 00:00:59 gives 287082. If this drifts, every authenticator
    app in the world is right and this code is wrong."""
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of that string
    assert two_factor.totp_at(secret, 1) == "287082"


def test_a_code_from_one_step_ago_still_works():
    secret = two_factor.new_secret()
    now = time.time()
    previous = two_factor.totp_at(secret, int(now // 30) - 1)
    assert two_factor.verify_totp(secret, previous, at=now)


def test_a_code_from_five_minutes_ago_does_not():
    secret = two_factor.new_secret()
    now = time.time()
    stale = two_factor.totp_at(secret, int(now // 30) - 10)
    assert not two_factor.verify_totp(secret, stale, at=now)


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "  "])
def test_nonsense_is_not_a_code(bad):
    assert not two_factor.verify_totp(two_factor.new_secret(), bad)


def test_the_qr_carries_the_secret_and_stays_on_this_server(db):
    user = db.get(User, 1)
    secret = two_factor.new_secret()
    uri = two_factor.provisioning_uri(user, secret)
    assert uri.startswith("otpauth://totp/EMCargo%3Aada?")
    assert secret in uri
    svg = two_factor.qr_svg(uri)
    assert svg.lstrip().startswith("<svg")
    # Drawn here, not fetched: an <img> pointing at a QR service would send
    # the shared secret to somebody else's server. (The xmlns is a namespace
    # name, not an address anything is loaded from.)
    body = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "http" not in body
    assert "<image" not in body and "href" not in body


# --- enrolment --------------------------------------------------------------


def test_an_unconfirmed_enrolment_changes_nothing_about_signing_in(client, db):
    two_factor.start_enrolment(db, db.get(User, 1), "totp")
    assert two_factor.is_active(db, 1) is False
    response = client.post("/api/auth/login", json={
        "username": "ada", "password": "old-password"})
    assert response.status_code == 200
    assert "two_factor_required" not in response.json()


def test_setting_up_totp_hands_back_a_secret_and_then_recovery_codes(signed_in, db):
    setup = signed_in.post("/api/auth/two-factor/start", json={"method": "totp"})
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["qr_svg"]

    wrong = signed_in.post("/api/auth/two-factor/confirm", json={"code": "000000"})
    assert wrong.status_code == 400
    assert two_factor.is_active(db, 1) is False

    code = two_factor.totp_at(secret, int(time.time() // 30))
    confirmed = signed_in.post("/api/auth/two-factor/confirm", json={"code": code})
    assert confirmed.status_code == 200
    codes = confirmed.json()["recovery_codes"]
    assert len(codes) == two_factor.RECOVERY_CODE_COUNT
    assert two_factor.is_active(db, 1) is True


def test_the_recovery_codes_are_stored_as_hashes(signed_in, db):
    setup = signed_in.post("/api/auth/two-factor/start", json={"method": "totp"})
    code = two_factor.totp_at(setup.json()["secret"], int(time.time() // 30))
    codes = signed_in.post("/api/auth/two-factor/confirm",
                           json={"code": code}).json()["recovery_codes"]
    from app.models.two_factor import TwoFactorRecoveryCode

    stored = {row.code_hash for row in db.query(TwoFactorRecoveryCode).all()}
    assert not (set(codes) & stored)
    assert two_factor.hash_code(codes[0]) in stored


def test_the_mail_method_needs_a_mail_server_and_says_so(signed_in, db, monkeypatch):
    monkeypatch.setattr(auth_route, "instance_settings",
                        lambda db: InstanceSettings())
    response = signed_in.post("/api/auth/two-factor/start", json={"method": "email"})
    assert response.status_code == 400
    assert "mail server" in response.json()["detail"]


def test_the_mail_method_confirms_with_the_code_that_was_sent(signed_in, db, sent):
    response = signed_in.post("/api/auth/two-factor/start", json={"method": "email"})
    assert response.status_code == 200 and response.json()["code_sent"] is True
    code = code_in(sent[-1])
    assert signed_in.post("/api/auth/two-factor/confirm",
                          json={"code": code}).status_code == 200
    assert two_factor.is_active(db, 1) is True


# --- signing in -------------------------------------------------------------


def enable_totp(db, user_id: int = 1) -> str:
    user = db.get(User, user_id)
    row = two_factor.start_enrolment(db, user, "totp")
    two_factor.confirm_enrolment(db, user)
    return row.secret


def test_a_password_alone_no_longer_signs_you_in(client, db):
    enable_totp(db)
    response = client.post("/api/auth/login", json={
        "username": "ada", "password": "old-password"})
    assert response.status_code == 200
    body = response.json()
    assert body["two_factor_required"] is True and body["challenge"]
    assert "access_token" not in response.cookies
    assert "user" not in body


def test_the_challenge_is_refused_as_a_session(client, db):
    """Half a sign-in, presented as a whole one."""
    enable_totp(db)
    challenge = client.post("/api/auth/login", json={
        "username": "ada", "password": "old-password"}).json()["challenge"]
    response = client.get("/api/auth/me", cookies={"access_token": challenge})
    assert response.status_code == 401


def test_the_right_code_finishes_the_sign_in(client, db):
    secret = enable_totp(db)
    challenge = client.post("/api/auth/login", json={
        "username": "ada", "password": "old-password"}).json()["challenge"]
    response = client.post("/api/auth/login/two-factor", json={
        "challenge": challenge,
        "code": two_factor.totp_at(secret, int(time.time() // 30))})
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "ada"


def test_a_wrong_code_does_not(client, db):
    enable_totp(db)
    challenge = client.post("/api/auth/login", json={
        "username": "ada", "password": "old-password"}).json()["challenge"]
    response = client.post("/api/auth/login/two-factor", json={
        "challenge": challenge, "code": "000000"})
    assert response.status_code == 401


def test_another_accounts_code_does_not_open_this_one(client, db):
    """The code is checked against the account in the challenge, not against
    whichever account happens to have a matching one."""
    enable_totp(db, 1)
    bobs_secret = enable_totp(db, 2)
    challenge = client.post("/api/auth/login", json={
        "username": "ada", "password": "old-password"}).json()["challenge"]
    response = client.post("/api/auth/login/two-factor", json={
        "challenge": challenge,
        "code": two_factor.totp_at(bobs_secret, int(time.time() // 30))})
    assert response.status_code == 401


def test_a_recovery_code_gets_you_in_once(client, db):
    user = db.get(User, 1)
    two_factor.start_enrolment(db, user, "totp")
    codes = two_factor.confirm_enrolment(db, user)

    def attempt(code):
        challenge = client.post("/api/auth/login", json={
            "username": "ada", "password": "old-password"}).json()["challenge"]
        return client.post("/api/auth/login/two-factor",
                           json={"challenge": challenge, "code": code})

    assert attempt(codes[0]).status_code == 200
    assert attempt(codes[0]).status_code == 401
    assert attempt(codes[1]).status_code == 200
    assert two_factor.unused_recovery_codes(db, 1) == len(codes) - 2


def test_a_password_changed_since_the_challenge_invalidates_it(client, db):
    secret = enable_totp(db)
    challenge = client.post("/api/auth/login", json={
        "username": "ada", "password": "old-password"}).json()["challenge"]
    ada = db.get(User, 1)
    ada.password_hash = hash_password("changed-in-another-window")
    db.commit()
    response = client.post("/api/auth/login/two-factor", json={
        "challenge": challenge,
        "code": two_factor.totp_at(secret, int(time.time() // 30))})
    assert response.status_code == 401


def test_an_invented_challenge_is_refused(client, db):
    enable_totp(db)
    response = client.post("/api/auth/login/two-factor", json={
        "challenge": "x" * 40, "code": "000000"})
    assert response.status_code == 401


def test_a_session_token_is_not_a_challenge(client, db):
    """The two are separate kinds of proof; swapping one for the other is the
    mistake the claim exists to prevent."""
    from app.core.security import create_access_token

    enable_totp(db)
    ada = db.get(User, 1)
    session = create_access_token(ada.username, password_hash=ada.password_hash)
    response = client.post("/api/auth/login/two-factor", json={
        "challenge": session, "code": "000000"})
    assert response.status_code == 401


def test_the_challenge_says_it_is_one():
    token = create_challenge_token("ada", hash_password("x"))
    from app.core.security import decode_access_token_claims

    assert decode_access_token_claims(token)[CHALLENGE_CLAIM] is True


# --- mailed sign-in codes ---------------------------------------------------


def test_signing_in_with_the_mail_method_sends_a_code(client, db, sent):
    user = db.get(User, 1)
    two_factor.start_enrolment(db, user, "email")
    two_factor.confirm_enrolment(db, user)

    response = client.post("/api/auth/login", json={
        "username": "ada", "password": "old-password"})
    body = response.json()
    assert body["method"] == "email" and body["code_sent"] is True

    finished = client.post("/api/auth/login/two-factor", json={
        "challenge": body["challenge"], "code": code_in(sent[-1])})
    assert finished.status_code == 200


def test_a_mailed_code_dies_after_five_wrong_guesses(db):
    user = db.get(User, 1)
    two_factor.start_enrolment(db, user, "email")
    two_factor.confirm_enrolment(db, user)
    code = two_factor.issue_email_code(db, user.id)
    for _ in range(two_factor.EMAIL_CODE_MAX_ATTEMPTS):
        assert two_factor.verify_email_code(db, user.id, "000000") is False
    # Even the right one, now: guessing has to cost something.
    assert two_factor.verify_email_code(db, user.id, code) is False


def test_an_expired_mailed_code_is_refused(db):
    user = db.get(User, 1)
    code = two_factor.issue_email_code(db, user.id)
    row = db.query(TwoFactorCode).order_by(TwoFactorCode.id.desc()).first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert two_factor.verify_email_code(db, user.id, code) is False


def test_asking_again_leaves_only_the_newest_code_alive(db):
    user = db.get(User, 1)
    first = two_factor.issue_email_code(db, user.id)
    second = two_factor.issue_email_code(db, user.id)
    assert two_factor.verify_email_code(db, user.id, first) is False
    assert two_factor.verify_email_code(db, user.id, second) is True


# --- switching it off -------------------------------------------------------


def test_turning_it_off_needs_a_working_code(signed_in, db):
    secret = enable_totp(db)
    refused = signed_in.request("DELETE", "/api/auth/two-factor",
                                json={"code": "000000"})
    assert refused.status_code == 400
    assert two_factor.is_active(db, 1) is True

    ok = signed_in.request("DELETE", "/api/auth/two-factor", json={
        "code": two_factor.totp_at(secret, int(time.time() // 30))})
    assert ok.status_code == 200
    assert two_factor.is_active(db, 1) is False


def test_it_cannot_be_switched_off_where_the_installation_requires_it(
        signed_in, db, monkeypatch):
    secret = enable_totp(db)
    monkeypatch.setattr(auth_route, "instance_settings",
                        lambda db: InstanceSettings(two_factor_policy="everyone"))
    response = signed_in.request("DELETE", "/api/auth/two-factor", json={
        "code": two_factor.totp_at(secret, int(time.time() // 30))})
    assert response.status_code == 400
    assert two_factor.is_active(db, 1) is True


def test_a_working_factor_is_not_restarted_without_a_code(signed_in, db):
    """Starting an enrolment over a confirmed one replaced the factor with
    the caller's own, from a borrowed session, without a code — the very
    thing switching it off is careful to demand. Refused since v1.190.0."""
    secret = enable_totp(db)
    for method in ("totp", "email"):
        refused = signed_in.post("/api/auth/two-factor/start", json={"method": method})
        assert refused.status_code == 400
    assert two_factor.is_active(db, 1) is True
    assert two_factor.enrolment_for(db, 1).secret == secret


def test_a_session_alone_cannot_replace_recovery_codes(signed_in, db):
    """Recovery codes are a second factor. Minting them with only a session
    bypassed the code required to switch that factor off, allowing a stolen
    session to replace the owner's backup proof without their phone."""
    from app.models.two_factor import TwoFactorRecoveryCode

    enable_totp(db)
    previous = {row.code_hash for row in db.query(TwoFactorRecoveryCode).all()}
    missing = signed_in.post("/api/auth/two-factor/recovery-codes")
    refused = signed_in.post("/api/auth/two-factor/recovery-codes", json={"code": "WRONG-CODE"})
    assert missing.status_code == 422
    assert refused.status_code == 400
    assert refused.json()["detail"]["code"] == "auth.two_factor_invalid_code"
    assert {row.code_hash for row in db.query(TwoFactorRecoveryCode).all()} == previous


@pytest.mark.parametrize("method", ["totp", "email", "recovery"])
def test_replacing_recovery_codes_accepts_each_existing_proof_and_revokes_old_ones(signed_in, db, method):
    """Someone who lost a phone can renew backups with an existing recovery
    code; mailbox and authenticator users can do the same with their factor.
    All old backups must cease to work, and no secret belongs in the audit."""
    from app.models.audit import AuditEvent

    user = db.get(User, 1)
    row = two_factor.start_enrolment(db, user, "email" if method == "email" else "totp")
    old_codes = two_factor.confirm_enrolment(db, user)
    proof = (two_factor.issue_email_code(db, user.id) if method == "email" else
             old_codes[0] if method == "recovery" else
             two_factor.totp_at(row.secret, int(time.time() // 30)))
    answer = signed_in.post("/api/auth/two-factor/recovery-codes", json={"code": proof})
    assert answer.status_code == 200
    fresh = answer.json()["recovery_codes"]
    assert len(fresh) == two_factor.RECOVERY_CODE_COUNT
    assert not set(fresh) & set(old_codes)
    assert all(not two_factor.spend_recovery_code(db, user.id, code) for code in old_codes)
    assert two_factor.spend_recovery_code(db, user.id, fresh[0])
    events = db.query(AuditEvent).filter_by(action="auth.recovery_codes_replaced").all()
    assert len(events) == 1
    assert events[0].actor_id == user.id
    assert all(code not in events[0].summary for code in [*old_codes, *fresh, proof])


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/auth/two-factor/confirm"),
    ("POST", "/api/auth/two-factor/recovery-codes"),
    ("DELETE", "/api/auth/two-factor"),
])
def test_second_factor_management_limits_code_guesses(signed_in, db, monkeypatch, method, path):
    """Protect every code-verifying management route, not only login. A
    stolen session otherwise offers unlimited guesses of a six-digit TOTP."""
    enable_totp(db)
    monkeypatch.setattr(auth_route.limiter, "enabled", True)
    statuses = [signed_in.request(method, path, json={"code": "WRONG-CODE"}).status_code
                for _ in range(11)]
    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429


def test_an_administrator_can_clear_a_lost_factor(client, db):
    enable_totp(db, 2)
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    response = client.delete("/api/users/2/two-factor")
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert two_factor.is_active(db, 2) is False
    # And everything that belonged to it is gone, not orphaned.
    assert db.query(TwoFactorEnrolment).filter(
        TwoFactorEnrolment.user_id == 2).count() == 0


# --- the policy -------------------------------------------------------------


@pytest.mark.parametrize("policy,role,expected", [
    ("off", "admin", False),
    ("off", "user", False),
    ("admins", "admin", True),
    ("admins", "user", False),
    ("everyone", "admin", True),
    ("everyone", "user", True),
])
def test_who_the_policy_covers(policy, role, expected):
    user = User(username="x", email="x@example.com", password_hash="x", role=role)
    assert two_factor.required_for(user, policy) is expected


def test_someone_who_owes_a_factor_is_told_so_rather_than_locked_out(
        signed_in, db, monkeypatch):
    """Requiring it must not shut people out of accounts they can still
    reach today; they are sent to set one up instead."""
    monkeypatch.setattr(auth_route, "instance_settings",
                        lambda db: InstanceSettings(two_factor_policy="everyone"))
    body = signed_in.get("/api/auth/me").json()
    assert body["two_factor_required"] is True
    assert body["two_factor_active"] is False


def test_a_required_factor_is_required_on_every_call_not_only_mentioned(client, db, monkeypatch):
    """The screen sends the account to set one up; the server makes sure it
    can reach nothing else until it has. Until v1.190.0 the policy was a
    notice with a stern face and every route let the session through."""
    from app.services import settings_store

    everyone = lambda db: InstanceSettings(two_factor_policy="everyone")  # noqa: E731
    monkeypatch.setattr(settings_store, "instance_settings", everyone)
    monkeypatch.setattr(auth_route, "instance_settings", everyone)
    signed = client.post("/api/auth/login", json={"username": "ada", "password": "old-password"})
    assert signed.status_code == 200
    # What the panel needs stays open: who am I, the factor, my preferences.
    assert client.get("/api/auth/me").json()["two_factor_required"] is True
    assert client.get("/api/auth/two-factor").status_code == 200
    assert client.get("/api/settings/me").status_code == 200
    # The work does not.
    refused = client.get("/api/settings/instance")
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "auth.two_factor_required"
    assert client.get("/api/equipment").status_code == 403
    # Confirmed, everything opens again.
    enable_totp(db)
    assert client.get("/api/settings/instance").status_code == 200


def test_the_policy_is_off_until_an_administrator_says_otherwise():
    assert InstanceSettings().two_factor_policy == "off"


# --- switching the mail method off ------------------------------------------


def test_the_mail_method_can_ask_for_a_code_to_switch_itself_off(signed_in, db, sent):
    """Turning it off needs a code, and with this method a code exists only
    once one has been sent. Without this the setting could be switched on
    and never off again."""
    user = db.get(User, 1)
    two_factor.start_enrolment(db, user, "email")
    two_factor.confirm_enrolment(db, user)
    sent.clear()

    asked = signed_in.post("/api/auth/two-factor/send-code")
    assert asked.status_code == 200
    code = code_in(sent[-1])

    off = signed_in.request("DELETE", "/api/auth/two-factor", json={"code": code})
    assert off.status_code == 200
    assert two_factor.is_active(db, 1) is False


def test_an_authenticator_account_is_not_offered_a_mailed_code(signed_in, db, sent):
    """It has one on the phone; mailing another would be a second way in
    that the owner never asked for."""
    enable_totp(db)
    response = signed_in.post("/api/auth/two-factor/send-code")
    assert response.status_code == 400
    assert sent == []


def test_an_account_without_a_second_factor_gets_no_code_either(signed_in, db, sent):
    response = signed_in.post("/api/auth/two-factor/send-code")
    assert response.status_code == 400
    assert sent == []
