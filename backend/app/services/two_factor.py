"""The second factor: an authenticator app, or a code by mail.

TOTP is implemented here rather than pulled in, because RFC 6238 is a
truncated HMAC-SHA1 over a counter of thirty-second steps and the standard
library already has every piece. A dependency would be more code to trust,
not less.

What the rest of the application should know about this module:

* an enrolment is not real until a first code has been checked — scanning a
  QR and closing the page must not lock anybody out;
* every code is compared in constant time and every attempt is counted;
* recovery codes and mailed codes are stored as hashes, like passwords;
* the clock is allowed to be one step out on either side, which is what a
  phone that has not synced in a week looks like.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.two_factor import (
    TwoFactorCode,
    TwoFactorEnrolment,
    TwoFactorRecoveryCode,
)
from app.models.user import User

#: The two ways in. Both are offered; which one an account uses is its
#: owner's choice, because a phone with an authenticator app is not
#: something every colleague has and a mailbox is not something everybody
#: wants standing between them and their work.
METHODS = ("totp", "email")

#: RFC 6238 defaults, and what every authenticator app expects.
TOTP_DIGITS = 6
TOTP_PERIOD = 30
#: One step either way: a phone whose clock drifted, or a code typed as the
#: window turns over. Wider than that starts to matter.
TOTP_DRIFT_STEPS = 1

#: A mailed code has to survive walking to another device and back.
EMAIL_CODE_TTL_MINUTES = 5
#: Six digits is a million possibilities: enough against a person, nothing
#: against a script, so the guesses are counted and the code dies at five.
EMAIL_CODE_MAX_ATTEMPTS = 5

RECOVERY_CODE_COUNT = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime) -> datetime:
    """SQLite hands back naive datetimes; they were written in UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


# --- TOTP -------------------------------------------------------------------


def new_secret() -> str:
    """A fresh shared secret, base32 without padding — what apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp(secret: str, code: str, at: float | None = None) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    counter = int((at if at is not None else time.time()) // TOTP_PERIOD)
    for step in range(-TOTP_DRIFT_STEPS, TOTP_DRIFT_STEPS + 1):
        if hmac.compare_digest(totp_at(secret, counter + step), code):
            return True
    return False


def provisioning_uri(user: User, secret: str, issuer: str = "EMCargo") -> str:
    """The otpauth: URI an authenticator app reads from the QR code."""
    from urllib.parse import quote

    label = quote(f"{issuer}:{user.username}", safe="")
    return (f"otpauth://totp/{label}?secret={secret}"
            f"&issuer={quote(issuer, safe='')}&digits={TOTP_DIGITS}"
            f"&period={TOTP_PERIOD}")


def qr_svg(uri: str) -> str:
    """The same URI as an SVG, small enough to inline in the page.

    An <img> pointing at a QR service would send the shared secret to
    somebody else's server, which is precisely the thing not to do with a
    shared secret.
    """
    import io

    import segno

    buffer = io.BytesIO()
    # No XML declaration: this goes inside a page, not into a file of its
    # own. Black on its own white field, in both themes — a camera reads
    # contrast, and a QR tinted to match a dark background reads badly or
    # not at all.
    segno.make(uri, error="m").save(buffer, kind="svg", scale=5, border=2,
                                    xmldecl=False, svgns=True,
                                    dark="#000000", light="#ffffff",
                                    svgclass=None, lineclass=None)
    return buffer.getvalue().decode("utf-8")


# --- enrolment --------------------------------------------------------------


def enrolment_for(db: Session, user_id: int) -> TwoFactorEnrolment | None:
    return (db.query(TwoFactorEnrolment)
            .filter(TwoFactorEnrolment.user_id == user_id).first())


def is_active(db: Session, user_id: int) -> bool:
    row = enrolment_for(db, user_id)
    return bool(row and row.confirmed)


class AlreadyEnrolled(ValueError):
    """A confirmed second factor is in place; it is switched off with a
    code first, never quietly replaced."""


def start_enrolment(db: Session, user: User, method: str) -> TwoFactorEnrolment:
    """Begin (or restart) setting up a second factor.

    Unconfirmed by design: nothing about the sign-in changes until the owner
    has proved they can produce a code. An enrolment that *is* confirmed is
    not restarted from here: until v1.190.0 it was, which let a borrowed
    session replace a working factor with its own without ever producing a
    code — the one thing switching it off is careful to demand.
    """
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    row = enrolment_for(db, user.id)
    if row is not None and row.confirmed:
        raise AlreadyEnrolled("A second factor is already switched on.")
    if row is None:
        row = TwoFactorEnrolment(user_id=user.id)
        db.add(row)
    row.method = method
    row.secret = new_secret() if method == "totp" else ""
    row.confirmed = False
    db.commit()
    db.refresh(row)
    return row


def confirm_enrolment(db: Session, user: User) -> list[str]:
    """Switch the second factor on and hand out fresh recovery codes."""
    row = enrolment_for(db, user.id)
    if row is None:
        raise ValueError("no enrolment to confirm")
    row.confirmed = True
    db.commit()
    return replace_recovery_codes(db, user)


def disable(db: Session, user_id: int) -> None:
    """Remove the second factor and everything that belonged to it."""
    for model in (TwoFactorEnrolment, TwoFactorRecoveryCode, TwoFactorCode):
        db.query(model).filter(model.user_id == user_id).delete(
            synchronize_session=False)
    db.commit()


# --- recovery codes ---------------------------------------------------------


def _readable_code() -> str:
    """Ten characters in two groups, from an alphabet without look-alikes.

    These get written down on paper and typed back in months later; 0/O and
    1/l cost more in wrong guesses than the alphabet saves in entropy.
    """
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    body = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"{body[:5]}-{body[5:]}"


def replace_recovery_codes(db: Session, user: User) -> list[str]:
    """New codes, returned once. Only their hashes stay behind."""
    db.query(TwoFactorRecoveryCode).filter(
        TwoFactorRecoveryCode.user_id == user.id).delete(synchronize_session=False)
    codes = [_readable_code() for _ in range(RECOVERY_CODE_COUNT)]
    for code in codes:
        db.add(TwoFactorRecoveryCode(user_id=user.id, code_hash=hash_code(code)))
    db.commit()
    return codes


def unused_recovery_codes(db: Session, user_id: int) -> int:
    return (db.query(TwoFactorRecoveryCode)
            .filter(TwoFactorRecoveryCode.user_id == user_id,
                    TwoFactorRecoveryCode.used_at.is_(None)).count())


def spend_recovery_code(db: Session, user_id: int, code: str) -> bool:
    row = (db.query(TwoFactorRecoveryCode)
           .filter(TwoFactorRecoveryCode.user_id == user_id,
                   TwoFactorRecoveryCode.code_hash == hash_code(code),
                   TwoFactorRecoveryCode.used_at.is_(None))
           .first())
    if row is None:
        return False
    row.used_at = _now()
    db.commit()
    return True


# --- mailed codes -----------------------------------------------------------


def issue_email_code(db: Session, user_id: int) -> str:
    """A six-digit code, valid for a few minutes, returned once.

    Any earlier code for this account is dropped: two live codes means two
    chances for whoever is guessing.
    """
    db.query(TwoFactorCode).filter(
        TwoFactorCode.user_id == user_id,
        TwoFactorCode.used_at.is_(None)).delete(synchronize_session=False)
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(TwoFactorCode(
        user_id=user_id,
        code_hash=hash_code(code),
        expires_at=_now() + timedelta(minutes=EMAIL_CODE_TTL_MINUTES),
    ))
    db.commit()
    return code


def verify_email_code(db: Session, user_id: int, code: str) -> bool:
    """Check a mailed code, counting the attempt either way."""
    row = (db.query(TwoFactorCode)
           .filter(TwoFactorCode.user_id == user_id,
                   TwoFactorCode.used_at.is_(None))
           .order_by(TwoFactorCode.id.desc())
           .first())
    if row is None:
        return False
    if _aware(row.expires_at) < _now() or row.attempts >= EMAIL_CODE_MAX_ATTEMPTS:
        return False
    row.attempts += 1
    if not hmac.compare_digest(row.code_hash, hash_code(code or "")):
        db.commit()
        return False
    row.used_at = _now()
    db.commit()
    return True


def verify(db: Session, user: User, code: str) -> bool:
    """Any proof this account can give: its own factor, or a recovery code.

    Recovery codes are accepted here rather than at a separate door, because
    somebody whose phone is in a canal should not have to find a different
    form to say so.
    """
    row = enrolment_for(db, user.id)
    if row is None or not row.confirmed:
        return False
    if row.method == "totp" and verify_totp(row.secret, code):
        return True
    if row.method == "email" and verify_email_code(db, user.id, code):
        return True
    return spend_recovery_code(db, user.id, code)


# --- the policy -------------------------------------------------------------


def required_for(user: User, policy: str) -> bool:
    """Whether this account must have a second factor under this policy."""
    if policy == "everyone":
        return True
    if policy == "admins":
        return user.role == "admin"
    return False
