"""Managing the UN card store: status, download, import, removal.

Admin-only throughout. The download endpoint fetches exclusively from the
pinned EMCargo release feed — no caller-supplied URL ever reaches the
server-side HTTP client — and both import paths run the same verification
and atomic swap in :mod:`app.services.documents.un_card_store`. Checking the
remote feed happens only when the administrator asks (``remote=true``);
nothing here phones home on its own.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.deps import require_admin
from app.models.user import User
from app.services.documents import un_card_store

router = APIRouter(prefix="/un-cards", tags=["un-cards"])

#: An uploaded package is written to disk in slices; anything beyond this is
#: refused before it fills the volume.
MAX_UPLOAD_BYTES = un_card_store.MAX_DOWNLOAD_BYTES


@router.get("/status")
def un_card_store_status(remote: bool = False, admin: User = Depends(require_admin)):
    local = un_card_store.status()
    if not remote:
        return {"local": local}
    try:
        return {"local": local, "remote": un_card_store.update_available()}
    except httpx.HTTPError as exc:
        # Not knowing is reported as not knowing — never as "up to date".
        return {"local": local, "remote": {"available": False, "reachable": False,
                                           "error": str(exc)}}


@router.post("/download-latest")
def download_and_import_latest(admin: User = Depends(require_admin)):
    """Fetch the newest published card set and install it atomically."""
    fd, name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    package = Path(name)
    try:
        remote = un_card_store.download_latest_package(package)
        result = un_card_store.import_package(package)
        return {"ok": True, "tag": remote.get("tag"), **result}
    except un_card_store.UnCardImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,
                            detail=f"The release could not be downloaded: {exc}") from exc
    finally:
        package.unlink(missing_ok=True)


@router.post("/import")
async def import_uploaded_package(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
):
    """Install a manually supplied emcargo-un-cards.zip.

    The same validation and atomic swap as the download path, so an
    air-gapped installation is not a less safe one.
    """
    fd, name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    package = Path(name)
    try:
        written = 0
        with package.open("wb") as sink:
            while True:
                chunk = await file.read(1 << 20)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413,
                                        detail="The upload exceeds the size limit.")
                sink.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="The upload is empty.")
        result = un_card_store.import_package(package)
        return {"ok": True, **result}
    except un_card_store.UnCardImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        package.unlink(missing_ok=True)


@router.post("/remove")
def remove_local_cards(admin: User = Depends(require_admin)):
    """Delete the installed set. The next status honestly says: nothing."""
    removed = un_card_store.remove_installed()
    return {"ok": True, "removed": removed}
