"""Profile photos must stay private, bounded and tied to the right account.

Exercise the real routes, decoder and database together: accepting a file is
not enough if another user can fetch it or deleting an account leaves its
photo attached to a subsequently reused ID.
"""
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.users import router
from app.core.database import Base, get_db
from app.core.deps import get_current_user
from app.models.user import User, UserAvatar
from app.schemas.users import UserOut
from app.services.avatars import MAX_UPLOAD_BYTES


def photo(color="navy"):
    output = BytesIO()
    exif = Image.Exif()
    exif[270] = "private-camera-metadata"
    Image.new("RGB", (600, 300), color).save(output, "JPEG", exif=exif)
    return output.getvalue()


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all([User(id=n, username=f"person{n}", email=f"person{n}@example.com", password_hash="unused", role="admin" if n == 1 else "user", active=True) for n in (1, 2, 3)])
        db.commit()
        app = FastAPI()
        app.include_router(router, prefix="/api")
        acting = {"id": 2}
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: db.get(User, acting["id"])
        with TestClient(app) as client:
            yield client, db, acting, app
    engine.dispose()


def upload(client, data=None):
    return client.post("/api/users/me/avatar", files={"file": ("../../photo.jpg", data if data is not None else photo(), "image/jpeg")})


def test_normalizes_and_persists_the_photo_without_camera_metadata(setup):
    client, db, _, _ = setup
    response = upload(client)
    assert response.status_code == 200
    url = response.json()["avatar_url"]
    db.expire_all()
    assert UserOut.model_validate(db.get(User, 2)).avatar_url == url
    image_response = client.get(url)
    assert image_response.headers["content-type"] == "image/webp"
    assert image_response.headers["cache-control"] == "private, no-cache"
    with Image.open(BytesIO(image_response.content)) as image:
        assert image.size == (256, 256)
        assert not image.getexif()
        assert "exif" not in image.info
    assert b"private-camera-metadata" not in image_response.content
    assert len(image_response.content) < 100_000
    assert client.get(url, headers={"If-None-Match": image_response.headers["etag"]}).status_code == 304


def test_only_the_owner_or_an_administrator_can_read_even_a_cached_photo(setup):
    client, _, acting, _ = setup
    url = upload(client).json()["avatar_url"]
    etag = client.get(url).headers["etag"]
    acting["id"] = 3
    assert client.get(url).status_code == 404
    assert client.get(url, headers={"If-None-Match": etag}).status_code == 404
    acting["id"] = 1
    assert client.get(url).status_code == 200
    listed = client.get("/api/users").json()
    assert next(user for user in listed if user["id"] == 2)["avatar_url"] == url


def test_replacement_changes_the_url_and_removal_removes_the_bytes(setup):
    client, db, _, _ = setup
    old = upload(client).json()["avatar_url"]
    new = upload(client, photo("gold")).json()["avatar_url"]
    assert old != new
    assert client.delete("/api/users/me/avatar").json()["avatar_url"] is None
    assert db.get(UserAvatar, 2) is None
    assert client.get(old).status_code == 404


def test_account_deletion_also_deletes_its_photo(setup):
    client, db, acting, _ = setup
    upload(client)
    acting["id"] = 1
    assert client.delete("/api/users/2").status_code == 200
    assert db.get(UserAvatar, 2) is None


@pytest.mark.parametrize("data", [b"", b"not an image", b'<svg xmlns="http://www.w3.org/2000/svg"><script>bad()</script></svg>'])
def test_bad_uploads_do_not_replace_a_saved_photo(setup, data):
    client, db, _, _ = setup
    original = upload(client).json()["avatar_url"]
    response = upload(client, data)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "avatar.invalid"
    assert UserOut.model_validate(db.get(User, 2)).avatar_url == original


def test_refuses_oversized_uploads_before_decoding(setup):
    client, _, _, _ = setup
    assert upload(client, b"x" * (MAX_UPLOAD_BYTES + 1)).status_code == 413


def test_anonymous_uploads_and_photo_reads_require_a_session(setup):
    client, _, _, app = setup
    app.dependency_overrides.pop(get_current_user)
    assert upload(client).status_code == 401
    assert client.get("/api/users/2/avatar").status_code == 401


def test_existing_user_tables_gain_the_avatar_table_without_changing_accounts():
    """The established create-all upgrade path adds the separate table while
    keeping old accounts valid; no avatar bytes are read for a user listing."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    UserAvatar.__table__.drop(engine)
    with engine.begin() as connection:
        connection.execute(User.__table__.insert().values(id=5, username="existing", email="existing@example.com", password_hash="unchanged", role="user", active=True))
    Base.metadata.create_all(engine)
    assert inspect(engine).has_table("user_avatars")
    with sessionmaker(bind=engine)() as db:
        user = db.get(User, 5)
        assert user.password_hash == "unchanged"
        assert UserOut.model_validate(user).avatar_url is None
    engine.dispose()
