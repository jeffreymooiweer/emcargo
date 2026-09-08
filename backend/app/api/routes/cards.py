"""The one route that needs no sign-in: the UN cards a QR code opens.

A QR code on a transport document is scanned by the driver at the roadside,
the warehouse taking the pallet in, the responder who arrived because
something went wrong. None of them has an account here, and a code that asks
them to log in is a code that does nothing. So this router is public, and
because it is public it is the narrowest thing in the application:

* it is **off unless an administrator turns it on** — a new door is a new
  door, and the person who owns the installation opens it rather than finding
  it open;
* it answers about **UN numbers only**, never about a consignment. There is no
  shipment to look up, which is also why the roadmap's question about link
  lifetime does not arise: the link addresses the regulation, and the
  regulation does not expire the way a stored job would;
* what it serves is the card set an administrator imported — EMCargo's own
  datasheets built from the measured tables. The document that carries the QR
  already prints those UN numbers in plain text and larger, so the code
  discloses nothing the paper does not;
* it is rate limited, because an unauthenticated route that reads files is
  exactly the shape of thing a script is pointed at.

A card that is not in the store is reported absent. It is never substituted
from another modality: the regimes print different obligations, and a card
that answers for the wrong one is worse than no card at all.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import CARD_LINKS, limiter
from app.services.documents.un_card_store import MODALITIES, card_path
from app.services.settings_store import instance_settings

router = APIRouter(prefix="/cards", tags=["cards"])

#: How many UN numbers one link may ask about. A transport document does not
#: carry fifty, and a cap keeps the public route from being turned into a
#: bulk reader of the whole store.
MAX_NUMBERS = 30


def _enabled(db: Session) -> None:
    if not instance_settings(db).card_links_enabled:
        # 404 rather than 403: an installation that has not opened this door
        # does not owe a stranger the information that the door exists.
        raise HTTPException(status_code=404, detail="Not found")


def _numbers(raw: str) -> list[str]:
    found: list[str] = []
    for part in re.split(r"[,\s]+", raw or ""):
        digits = re.sub(r"\D", "", part)
        if len(digits) == 4 and digits not in found:
            found.append(digits)
    return found[:MAX_NUMBERS]


@router.get("/lookup")
@limiter.limit(CARD_LINKS)
def card_lookup(
    request: Request,
    un: str = Query(default="", max_length=400),
    modality: str = Query(default="ADR", max_length=10),
    db: Session = Depends(get_db),
):
    """Which of these UN numbers this installation holds a card for.

    Reports the absent ones as plainly as the present ones. Somebody standing
    at a vehicle needs to know that a card is missing, not to be shown a
    shorter list and left to assume it was complete.
    """
    _enabled(db)
    wanted = str(modality).strip().upper()
    if wanted not in MODALITIES:
        raise HTTPException(status_code=400, detail="Unknown modality")
    numbers = _numbers(un)
    return {
        "modality": wanted,
        "cards": [
            {"un_number": number, "available": card_path(number, wanted) is not None}
            for number in numbers
        ],
    }


@router.get("/{un}/{modality}.pdf")
@limiter.limit(CARD_LINKS)
def card_file(
    request: Request,
    un: str,
    modality: str,
    db: Session = Depends(get_db),
):
    _enabled(db)
    path = card_path(un, str(modality).strip().upper())
    if path is None:
        raise HTTPException(status_code=404, detail="No card for this UN number")
    return FileResponse(path, media_type="application/pdf",
                        filename=path.name)
