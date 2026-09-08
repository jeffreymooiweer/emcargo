"""The installation's name and pictures.

Reading branding is public so it can paint the sign-in page. Changing it is
restricted to administrators. Operators may also provide the same image files
in DATA_DIR/branding.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.user import User
from app.schemas.settings import MODALITIES
from app.services import branding
from app.services.settings_store import instance_settings

public_router = APIRouter(prefix="/branding", tags=["branding"])
admin_router = APIRouter(prefix="/branding", tags=["branding"])

#: Long, because the address carries the file's modification time: a changed
#: picture is a different address, so the old one may be kept indefinitely.
CACHE = "public, max-age=31536000, immutable"


@public_router.get("")
def branding_status(db: Session = Depends(get_db)):
    """The name and the addresses of whatever pictures are uploaded.

    ``null`` where the default applies, so the interface draws its own
    picture rather than asking for one that is not there.
    """
    return {"name": instance_settings(db).brand_name, **branding.assets()}


def _serve(name: str) -> Response:
    found = branding.asset(name)
    if not found:
        raise HTTPException(status_code=404, detail="No such image")
    path, media_type = found
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": CACHE})


@public_router.get("/logo")
def logo():
    return _serve("logo")


@public_router.get("/modality/{key}")
def modality_image(key: str):
    if key not in MODALITIES:
        raise HTTPException(status_code=404, detail="No such transport mode")
    return _serve(key)


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    """The upload's bytes, refused past the cap before they are all held."""
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(1 << 18)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"The image exceeds the {limit // 1024 // 1024} MB limit.")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=400, detail="The upload is empty.")
    return b"".join(chunks)


async def _replace(name: str, file: UploadFile) -> dict:
    data = await _read_upload(file, branding.limit_for(name))
    try:
        branding.store(name, data)
    except branding.BrandingError as exc:
        # Not an image we will show: the uploader's mistake, said plainly.
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    return {"ok": True, **branding.assets()}


@admin_router.post("/logo")
async def upload_logo(file: UploadFile = File(...),
                      admin: User = Depends(require_admin)):
    return await _replace("logo", file)


@admin_router.delete("/logo")
def remove_logo(admin: User = Depends(require_admin)):
    return {"ok": True, "removed": branding.remove("logo"), **branding.assets()}


@admin_router.post("/modality/{key}")
async def upload_modality_image(key: str, file: UploadFile = File(...),
                                admin: User = Depends(require_admin)):
    if key not in MODALITIES:
        raise HTTPException(status_code=404, detail="No such transport mode")
    return await _replace(key, file)


@admin_router.delete("/modality/{key}")
def remove_modality_image(key: str, admin: User = Depends(require_admin)):
    if key not in MODALITIES:
        raise HTTPException(status_code=404, detail="No such transport mode")
    return {"ok": True, "removed": branding.remove(key), **branding.assets()}
