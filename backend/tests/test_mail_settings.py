"""The mail server an administrator configures, and the guarantees around it.

Four things are pinned here, each of which this feature could plausibly have
shipped without.

1. **The password never leaves the server.** The settings screen is fetched on
   every visit; a stored SMTP password in that response is a secret handed to
   every browser that opens the screen. It is redacted on the way out, and a
   flag says whether one exists.

2. **Saving something else does not wipe the password.** Because the screen
   cannot receive the password, it cannot send it back — so an empty field has
   to mean "keep it". Without that rule, changing the port silently breaks
   sending.

3. **Switching mail on without a server fails where it can be seen.** An empty
   host would otherwise fail at the first message, long after anyone is
   watching.

4. **The reason a test fails is the server's own.** A refused password and an
   unreachable host are different problems with different fixes, and the
   administrator gets the sentence that distinguishes them.
"""
import smtplib

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.deps import get_current_user, require_admin
from app.main import app
from app.models.user import User
from app.schemas.settings import InstanceSettings
from app.services import mail, mail_templates, settings_store


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
                     password_hash="x", role="admin"))
    session.commit()
    yield session
    session.close()
    get_settings.cache_clear()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    app.dependency_overrides[require_admin] = lambda: db.get(User, 1)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def configured(**overrides) -> InstanceSettings:
    values = {
        "mail_enabled": True,
        "mail_host": "smtp.example.com",
        "mail_port": 587,
        "mail_from": "emcargo@example.com",
        "mail_from_name": "EMCargo",
        "mail_username": "emcargo",
        "mail_password": "secret",
    }
    values.update(overrides)
    return InstanceSettings(**values)


class FakeSMTP:
    """Enough of smtplib to see what was asked of the server."""

    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.started_tls = False
        self.login_as = None
        self.sent = []
        self.raises = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.started_tls = True

    def ehlo(self):
        pass

    def login(self, username, password):
        if self.raises:
            raise self.raises
        self.login_as = (username, password)

    def send_message(self, message):
        if self.raises:
            raise self.raises
        self.sent.append(message)


@pytest.fixture(autouse=True)
def clean_fakes():
    FakeSMTP.instances.clear()
    yield
    FakeSMTP.instances.clear()


# --- the schema -------------------------------------------------------------


def test_sending_without_a_server_is_refused_where_it_can_be_seen():
    with pytest.raises(ValidationError):
        InstanceSettings(mail_enabled=True, mail_host="", mail_from="a@b.nl")
    with pytest.raises(ValidationError):
        InstanceSettings(mail_enabled=True, mail_host="smtp.example.com", mail_from="")


def test_a_hostname_typed_into_the_sender_field_is_refused():
    with pytest.raises(ValidationError):
        InstanceSettings(mail_from="smtp.example.com")


def test_mail_is_off_and_empty_until_it_is_configured():
    default = InstanceSettings()
    assert default.mail_enabled is False
    assert default.mail_host == "" and default.mail_from == ""


# --- the secret -------------------------------------------------------------


def test_the_password_is_redacted_on_the_way_out():
    stored = settings_store.redacted(configured())
    assert stored.mail_password == ""


def test_a_stored_password_is_announced_rather_than_shown(db, client):
    client.put("/api/settings/instance", json=configured().model_dump(mode="json"))
    body = client.get("/api/settings/instance").json()
    assert body["mail_password"] == ""
    assert body["mail_password_set"] is True
    assert body["mail_host"] == "smtp.example.com"


def test_saving_without_a_password_keeps_the_stored_one(db):
    settings_store.save_instance_settings(db, configured())
    settings_store.save_instance_settings(
        db, configured(mail_port=465, mail_security="ssl", mail_password=""))
    current = settings_store.instance_settings(db)
    assert current.mail_password == "secret"
    assert current.mail_port == 465 and current.mail_security == "ssl"


def test_a_new_password_replaces_the_stored_one(db):
    settings_store.save_instance_settings(db, configured())
    settings_store.save_instance_settings(db, configured(mail_password="another"))
    assert settings_store.instance_settings(db).mail_password == "another"


def test_the_flag_is_derived_and_not_taken_from_the_caller(db):
    """A caller claiming a password exists must not make one exist."""
    settings_store.save_instance_settings(
        db, configured(mail_password="", mail_password_set=True))
    assert settings_store.instance_settings(db).mail_password_set is False


# --- sending ----------------------------------------------------------------


def test_starttls_is_negotiated_and_the_login_is_the_configured_one(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mail.send(configured(), "ada@example.com", "Subject", "Body")
    server = FakeSMTP.instances[-1]
    assert (server.host, server.port) == ("smtp.example.com", 587)
    assert server.started_tls is True
    assert server.login_as == ("emcargo", "secret")
    assert server.sent[0]["To"] == "ada@example.com"
    assert server.sent[0]["From"] == "EMCargo <emcargo@example.com>"


def test_direct_tls_uses_the_ssl_client_and_does_not_start_tls(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    mail.send(configured(mail_security="ssl", mail_port=465), "ada@example.com", "S", "B")
    server = FakeSMTP.instances[-1]
    assert server.port == 465 and server.started_tls is False


def test_a_relay_without_a_user_name_is_not_asked_to_log_in(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mail.send(configured(mail_username="", mail_password="", mail_security="none"),
              "ada@example.com", "S", "B")
    server = FakeSMTP.instances[-1]
    assert server.login_as is None and server.started_tls is False


def test_without_a_mail_server_nothing_is_sent():
    with pytest.raises(mail.MailError, match="No mail server is configured"):
        mail.send(InstanceSettings(), "ada@example.com", "S", "B")


def test_a_refused_password_says_so(monkeypatch):
    def failing(*args, **kwargs):
        server = FakeSMTP(*args, **kwargs)
        server.raises = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        return server

    monkeypatch.setattr(smtplib, "SMTP", failing)
    with pytest.raises(mail.MailError) as exc:
        mail.send(configured(), "ada@example.com", "S", "B")
    assert "refused the user name or password" in str(exc.value)
    assert "Username and Password not accepted" in str(exc.value)


def test_an_unreachable_server_names_host_and_port(monkeypatch):
    def refusing(*args, **kwargs):
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr(smtplib, "SMTP", refusing)
    with pytest.raises(mail.MailError) as exc:
        mail.send(configured(), "ada@example.com", "S", "B")
    assert "smtp.example.com:587" in str(exc.value)


# --- the test button --------------------------------------------------------


def test_the_test_message_goes_to_the_administrator_by_default(db, client, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    client.put("/api/settings/instance", json=configured().model_dump(mode="json"))
    response = client.post("/api/settings/instance/mail-test", json={"to": ""})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "to": "ada@example.com"}
    assert FakeSMTP.instances[-1].sent[0]["Subject"] == \
        mail_templates.test_message("nl").subject


def test_the_test_uses_the_stored_password_the_screen_never_saw(db, client, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    client.put("/api/settings/instance", json=configured().model_dump(mode="json"))
    # What the screen sends back after an edit: no password in it.
    redacted = client.get("/api/settings/instance").json()
    redacted["mail_port"] = 2525
    client.put("/api/settings/instance", json=redacted)
    client.post("/api/settings/instance/mail-test", json={"to": "bob@example.com"})
    assert FakeSMTP.instances[-1].login_as == ("emcargo", "secret")


def test_a_failing_test_answers_400_with_what_the_server_said(db, client, monkeypatch):
    def refusing(*args, **kwargs):
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr(smtplib, "SMTP", refusing)
    client.put("/api/settings/instance", json=configured().model_dump(mode="json"))
    response = client.post("/api/settings/instance/mail-test", json={"to": "ada@example.com"})
    assert response.status_code == 400
    assert "smtp.example.com:587" in response.json()["detail"]


def test_a_test_without_a_mail_server_is_refused_rather_than_silent(db, client):
    response = client.post("/api/settings/instance/mail-test", json={"to": "ada@example.com"})
    assert response.status_code == 400
    assert "No mail server is configured" in response.json()["detail"]


def test_the_recipient_must_look_like_an_address(db, client):
    response = client.post("/api/settings/instance/mail-test", json={"to": "not-an-address"})
    assert response.status_code == 422
