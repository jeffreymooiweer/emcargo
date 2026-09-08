"""Who a rate limit counts against.

``slowapi.util.get_remote_address`` returns ``request.client.host`` and never
reads ``X-Forwarded-For``. That is correct for a container someone reaches
directly and wrong for every installation that terminates TLS behind a reverse
proxy — which is most of them, and all of the ones on the public internet. There
every caller arrives wearing the proxy's address, so they share one bucket:
fifteen colleagues behind one nginx shared the ten sign-in attempts a minute and
could lock each other out.

The header is not simply trusted instead. A caller can send an
``X-Forwarded-For`` of their own, and a proxy **appends** rather than replaces,
so the header the application sees is ``<what the caller claimed>, <what the
proxy actually saw>``. The leftmost entry is therefore the one under the
caller's control and the rightmost is the one the nearest proxy vouches for.
Reading the left of that list is not a smaller version of this fix; it is a rate
limiter with a bypass in it, because a caller who picks a fresh value per request
gets a fresh bucket per request.

So the entry is counted from the right, one position per proxy in front:

    client -> nginx -> app          "C"        take the 1st from the right
    client -> cdn -> nginx -> app   "C, cdn"   take the 2nd from the right

Forwarded headers are ignored by default. An operator whose backend is reachable
only through controlled proxies enables ``TRUSTED_PROXY_HEADERS=true`` explicitly.
``TRUSTED_PROXY_COUNT`` is their number and defaults to 1. When the header holds
fewer entries than there are proxies the installation is misconfigured, and this
falls back to the peer address: a limiter that counts everyone as one caller is
useless, but a limiter keyed on a value the caller chooses is worse.

**And the limiter itself lives here**, for a reason found while fixing the above.
There used to be two: one built in ``main.py`` and put on ``app.state``, and a
second built in ``api/routes/auth.py`` that carried every one of the six
``@limiter.limit`` decorators. Only the second enforced anything, so re-keying
the first changed nothing at all — a fix that would have shipped as a no-op and
tested green, because a unit test of the key function passes either way. One
limiter, defined in one place, imported by both.
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter

from app.core.config import get_settings

#: What slowapi falls back to when there is no peer at all (a test client, a
#: unix socket). Kept identical to ``get_remote_address`` so behaviour without
#: a proxy is unchanged.
NO_PEER = "127.0.0.1"


def _peer(request: Request) -> str:
    if not request.client or not request.client.host:
        return NO_PEER
    return request.client.host


def client_address(request: Request) -> str:
    """The address a rate limit is counted against."""
    settings = get_settings()
    if not settings.trusted_proxy_headers:
        return _peer(request)

    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not hops:
        return _peer(request)

    # One position per proxy in front of us, counted from the right. Anything
    # further left than that was appended by something we do not vouch for.
    count = max(1, settings.trusted_proxy_count)
    if count > len(hops):
        return _peer(request)
    return hops[-count]


#: The application's one rate limiter. Import it; do not build another.
limiter = Limiter(key_func=client_address)


# What the expensive endpoints cost, and therefore what they are allowed.
#
# Each of these guards work an unauthenticated caller can ask for once the
# Open mode opens the application to one. Until then they guard against a
# signed-in caller with a script, which is a smaller problem but the same shape.
# The numbers are set from what a person doing the work actually does: a limit
# that a real user reaches is a bug report, not a defence.
#
# The sign-in limits are not here. They sit on their routes in
# ``api/routes/auth.py`` where they have always been, and
# ``test_ratelimit_key`` prints every limit in the application in one table so
# neither half can drift out of sight.

#: Rendering one document. The export step offers each paper separately and a
#: consignment can carry a dozen, so somebody working through them and then
#: correcting a field and going round again reaches a few dozen without doing
#: anything unusual. Rendering costs a fraction of a second, so the ceiling is
#: set to stay out of that person's way rather than to ration the work.
DOCUMENT_EXPORT = "60/minute"

#: The whole bundle: every document, the UN cards and the written instructions
#: in one archive. The most expensive thing a signed-in caller can ask for, and
#: nobody assembles more than a few.
DOCUMENT_BUNDLE = "10/minute"

#: The bundle, mailed. Lower than the bundle itself on purpose: this is the one
#: endpoint whose cost lands on somebody else — the recipient, and the sending
#: domain's reputation.
DOCUMENT_BUNDLE_MAIL = "5/minute"

#: UN card generation, per set.
UN_CARDS = "10/minute"

#: The safety adviser's annual report: every kept shipment of a year is
#: read and its export parsed, which is a few hundred JSON documents on a
#: busy installation. Drawn up a few times a year, never a few times a
#: minute — except by a script.
DGSA_REPORT = "20/minute"

#: Reading an uploaded carrier confirmation. File parsing, so the size of the
#: work is the caller's choice.
CARRIER_CONFIRMATION = "20/minute"

#: One turn of the assistant. With a model installed this is inference, which is
#: by a wide margin the most expensive thing in the application.
#:
#: The first number here was 20, on the reasoning that a conversation goes at
#: the speed somebody types. That was wrong, and the test suite said so within
#: the minute: the assistant is a *survey*, it offers every optional field it
#: could still fill in, and "skip" is one turn each. The archetype test walks
#: eighty of them, and so does a person who wants none of the optional fields —
#: clicking skip is far faster than typing. A limit a real user reaches is a bug
#: report, not a defence.
#:
#: So it is set where no person can arrive but a script is still capped: two a
#: second. With a model installed, inference is slower than that anyway, which
#: means this bounds the case that has no model and is merely cheap.
ASSISTANT_STEP = "120/minute"

#: Asking for the model to be downloaded. An administrator's button, and a
#: multi-gigabyte fetch behind it.
ASSISTANT_MODEL = "3/minute"

#: The public card links a QR code opens. The only route in the application
#: that answers without a sign-in, so its limit is the one that guards a
#: stranger rather than a colleague: generous enough for a driver whose phone
#: retries, far below what a script would want from a route that reads files.
CARD_LINKS = "30/minute"

#: One groupage assessment. It runs the points check once per consignment and
#: once more over the whole load, so its cost grows with the number of
#: consignments rather than being fixed like the other checks. A planner
#: assembling a vehicle does this a handful of times; nobody does it hundreds.
TRIP_CHECK = "30/minute"

#: Keeping the running entry as a draft. The interface saves a few seconds
#: after the typing stops, so a person filling in a shipment produces a handful
#: a minute; this bounds a script or a stuck retry loop, which would otherwise
#: rewrite one row as fast as the database allows.
DRAFT_SAVE = "60/minute"

#: Address autocomplete, which proxies to a Photon instance. The generous one,
#: and deliberately: the field debounces at 250 ms, so a person typing four
#: addresses into a consignment legitimately produces dozens of these. It is
#: here because the cost falls on somebody else's free service, not because a
#: person could plausibly exhaust it.
ADDRESS_LOOKUP = "60/minute"
