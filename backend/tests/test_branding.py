"""The installation's own name and pictures.

Uploaded images are user content, and the three rules at the edge are what
this file pins: the *bytes* decide what a file is, never its name or its
declared type; SVG is refused because it is a document that can carry script;
and the caps are enforced before the upload is held whole. Around that, the
plainer facts — a visitor can read the door before signing in, only an
administrator can repaint it, and the sign-in page serves files its operator
placed by hand, and the mail carries the same logo as the screen.
"""
from __future__ import annotations

import io
import struct
import zlib

import pytest

from tests import route_table
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.deps import get_current_user, require_admin
from app.main import app, create_app
from app.models.user import User
from app.schemas.settings import InstanceSettings
from app.services import branding, mail, mail_templates, settings_store


def png(width: int = 1, height: int = 1) -> bytes:
    """A real, tiny PNG: the sniffer reads magic bytes, but a test image that
    is only magic bytes teaches nothing about the round trip."""
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF" + struct.pack("<I", 64) + b"WEBP" + b"VP8 " + b"\x00" * 56
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.fixture
def db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CATALOG_AUTO_SYNC", "false")
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, username="ada", email="ada@example.com",
                     password_hash="x", role="admin"))
    session.add(User(id=2, username="bob", email="bob@example.com",
                     password_hash="x", role="user"))
    session.commit()
    yield session
    session.close()
    get_settings.cache_clear()


@pytest.fixture
def admin(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    app.dependency_overrides[require_admin] = lambda: db.get(User, 1)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def colleague(db):
    """Signed in, not an administrator. ``require_admin`` is left real."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 2)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def upload(client, path: str, data: bytes, filename: str = "image.png",
           content_type: str = "image/png"):
    return client.post(path, files={"file": (filename, io.BytesIO(data), content_type)})


# --- the door, before anybody signs in ---------------------------------------


def test_the_door_reads_without_a_session(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        response = client.get("/api/branding")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {
        "name": "",
        "logo": None,
        "modalities": {key: None for key in
                       ("road", "rail", "sea", "inland", "air", "multimodal")},
    }


def test_the_name_is_an_instance_setting_with_an_environment_start(admin, db, monkeypatch):
    settings_store.save_instance_settings(db, InstanceSettings(brand_name="  Mooiweer Logistiek "))
    assert admin.get("/api/branding").json()["name"] == "Mooiweer Logistiek"

    monkeypatch.setenv("BRAND_NAME", "Haven BV")
    get_settings.cache_clear()
    assert settings_store.environment_defaults().brand_name == "Haven BV"


# --- uploading ---------------------------------------------------------------


def test_a_logo_is_served_back_with_its_own_type_and_a_versioned_address(admin):
    response = upload(admin, "/api/branding/logo", png())
    assert response.status_code == 200, response.text
    url = response.json()["logo"]
    assert url.startswith("/api/branding/logo?v=")

    served = admin.get(url)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert "immutable" in served.headers["cache-control"]
    assert served.content == png()


def test_the_bytes_decide_what_a_file_is(admin):
    """A JPEG uploaded as ``logo.png`` with ``image/png`` declared is a JPEG,
    and is stored and served as one."""
    upload(admin, "/api/branding/logo", JPEG, filename="logo.png", content_type="image/png")
    assert branding.asset("logo")[0].suffix == ".jpg"
    assert admin.get("/api/branding/logo").headers["content-type"] == "image/jpeg"

    # And a WebP is a WebP.
    upload(admin, "/api/branding/modality/sea", WEBP, filename="sea.png")
    assert admin.get("/api/branding/modality/sea").headers["content-type"] == "image/webp"


@pytest.mark.parametrize("data", [SVG, b"not an image at all", b"\x89PNG only a start"])
def test_what_is_not_an_image_is_refused(admin, data):
    response = upload(admin, "/api/branding/logo", data, filename="logo.svg",
                      content_type="image/svg+xml")
    assert response.status_code == 415
    assert branding.asset("logo") is None


def test_an_empty_upload_is_refused(admin):
    assert upload(admin, "/api/branding/logo", b"").status_code == 400


def test_the_cap_is_enforced_before_the_upload_is_held_whole(admin):
    oversized = png() + b"\x00" * branding.MAX_LOGO_BYTES
    response = upload(admin, "/api/branding/logo", oversized)
    assert response.status_code == 413
    assert branding.asset("logo") is None
    # A tile may be larger than a logo, but not without limit either.
    tile = png() + b"\x00" * branding.MAX_MODALITY_BYTES
    assert upload(admin, "/api/branding/modality/road", tile).status_code == 413


def test_replacing_in_another_format_leaves_no_old_file_behind(admin):
    upload(admin, "/api/branding/modality/road", JPEG)
    upload(admin, "/api/branding/modality/road", png())
    folder = branding.directory()
    assert sorted(p.name for p in folder.iterdir()) == ["modality-road.png"]
    assert admin.get("/api/branding/modality/road").headers["content-type"] == "image/png"


def test_only_the_six_transport_modes_have_a_tile(admin):
    assert upload(admin, "/api/branding/modality/drone", png()).status_code == 404
    assert admin.get("/api/branding/modality/drone").status_code == 404
    assert admin.delete("/api/branding/modality/drone").status_code == 404


def test_removing_goes_back_to_the_default(admin):
    upload(admin, "/api/branding/logo", png())
    first = admin.delete("/api/branding/logo")
    assert first.json()["removed"] is True
    assert first.json()["logo"] is None
    assert admin.get("/api/branding/logo").status_code == 404
    # Removing twice is not an error: the second answer just says so.
    assert admin.delete("/api/branding/logo").json()["removed"] is False


def test_a_colleague_cannot_repaint_the_door(colleague):
    assert upload(colleague, "/api/branding/logo", png()).status_code == 403
    assert colleague.delete("/api/branding/logo").status_code == 403
    # But can look at it, like anybody.
    assert colleague.get("/api/branding").status_code == 200


def test_a_planted_file_with_another_extension_is_not_served(admin):
    folder = branding.directory()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "logo.html").write_text("<script>alert(1)</script>")
    assert branding.asset("logo") is None
    assert admin.get("/api/branding/logo").status_code == 404


# --- the mail carries the same logo as the screen ----------------------------


def test_the_mail_carries_the_uploaded_logo_with_the_right_subtype(admin, db):
    upload(admin, "/api/branding/logo", JPEG)
    assert mail_templates.logo_image() == (JPEG, "jpeg")

    message = mail_templates.test_message("nl")
    built = mail.build_message(
        InstanceSettings(mail_enabled=True, mail_host="smtp.example.com",
                         mail_from="emcargo@example.com"),
        "ada@example.com", message.subject, message.text, html=message.html)
    images = [p for p in built.walk() if p.get_content_maintype() == "image"]
    logo = next(p for p in images if p.get("Content-ID") == f"<{mail_templates.LOGO_CID}>")
    assert logo.get_content_type() == "image/jpeg"
    assert logo.get_payload(decode=True) == JPEG

    # Back to EMCargo's own once it is removed.
    admin.delete("/api/branding/logo")
    assert mail_templates.logo_image()[1] == "png"


# --- login branding ----------------------------------------------------


def test_login_branding_stays_public_while_changes_require_an_account(db, monkeypatch):
    """Existing branding files must still paint the sign-in page after upgrading,
    while an anonymous visitor must never be allowed to replace those files.
    """
    monkeypatch.setenv("EMCARGO_MODE", "open")
    monkeypatch.setenv("BRAND_NAME", "Example Haven")
    get_settings.cache_clear()
    folder = branding.directory()
    folder.mkdir(parents=True)
    (folder / "logo.png").write_bytes(png())
    (folder / "modality-rail.jpg").write_bytes(JPEG)

    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    with TestClient(application) as client:
        door = client.get("/api/branding").json()
        assert door["name"] == "Example Haven"
        assert door["logo"].startswith("/api/branding/logo?v=")
        assert door["modalities"]["rail"].startswith("/api/branding/modality/rail?v=")
        assert door["modalities"]["road"] is None
        assert client.get(door["logo"]).status_code == 200
        assert upload(client, "/api/branding/logo", png()).status_code == 401
        assert client.delete("/api/branding/logo").status_code == 401
        assert upload(client, "/api/branding/modality/rail", png()).status_code == 401
        assert any(a.path == "/api/branding" for a in route_table.addresses(application))
