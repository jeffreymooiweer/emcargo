"""Updating the application from inside it — deliberately, or not at all.

A container cannot swap its own image: the process would die halfway
through its own replacement. What it *can* do, when the operator has
mounted the Docker socket and set ``UPDATE_APPLY_ENABLED=true``, is pull
the newer image of itself and hand the actual swap to a short-lived
helper container **started from that new image** (`app.update_helper`):
the helper stops this container, renames it aside, creates a new one
with the identical configuration on the new image, starts it, and only
then removes the old one — and if the new one will not start, it puts
the old one back. The restart the user sees is the update happening.

Two honesty rules govern everything here:

* The capability is the operator's, not ours. Without the socket and the
  explicit switch, this module reports exactly why applying is not
  available; it never suggests the application could do something it
  cannot.
* The image reference is never caller input. The repository comes from
  this very container's own configuration, the tag from the release the
  update check found — ``repo:vX.Y.Z``, pulled by digestless tag from
  the same registry the operator installed from.

Progress survives the restart in ``<data-dir>/update-state.json``: the
new instance finds there whether it is the product of an update, and the
old instance's administrators find why one failed.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DOCKER_SOCKET = Path("/var/run/docker.sock")

#: The one image this application will update to. Pinned here as well as
#: read from the running container, so a container someone started from a
#: fork or a hand-built tag refuses rather than pulls something the
#: check's version number never described.
IMAGE_REPOSITORY = "ghcr.io/jeffreymooiweer/emcargo"

HELPER_NAME_PREFIX = "emcargo-updater"


class UpdateError(Exception):
    """A reason the update cannot proceed, phrased for the administrator."""


def state_file() -> Path:
    return get_settings().data_dir / "update-state.json"


def docker_client() -> httpx.Client:
    """An HTTP client speaking to the Docker daemon over its socket."""
    return httpx.Client(
        transport=httpx.HTTPTransport(uds=str(DOCKER_SOCKET)),
        base_url="http://docker",
        timeout=30.0,
    )


def own_container_id(client: httpx.Client) -> str | None:
    """This container's id, verified against the daemon.

    Docker sets the hostname to the short container id unless the operator
    chose one; when they did, the cgroup and mountinfo files still carry
    the full id. Every candidate is verified with an inspect call — a
    guess that the daemon does not recognise is no identity at all.
    """
    candidates: list[str] = []
    hostname = os.environ.get("HOSTNAME") or os.uname().nodename
    if re.fullmatch(r"[0-9a-f]{12,64}", hostname or ""):
        candidates.append(hostname)
    for path in ("/proc/self/mountinfo", "/proc/self/cgroup"):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        candidates.extend(re.findall(r"[0-9a-f]{64}", text))
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            response = client.get(f"/containers/{candidate}/json")
        except httpx.HTTPError:
            return None
        if response.status_code == 200:
            return str(response.json()["Id"])
    return None


def capability() -> dict[str, Any]:
    """What this installation can do about updating itself, and why not.

    Never raises: the answer is for the settings screen, and "not possible,
    because X" is the product, not an error.
    """
    settings = get_settings()
    method = (settings.install_method or "docker").strip().lower()
    result: dict[str, Any] = {
        "apply_enabled": bool(settings.update_apply_enabled),
        "socket": DOCKER_SOCKET.exists(),
        "container": None,
        "image": None,
        "available": False,
        "reason": None,
        "install_method": method if method in ("docker", "native", "kubernetes") else "docker",
    }
    # A native service or a pod has no container of its own to replace and
    # no socket to do it with; the screen names the route that applies.
    if result["install_method"] != "docker":
        result["reason"] = result["install_method"]
        return result
    if not result["apply_enabled"]:
        result["reason"] = "switch_off"
        return result
    if not result["socket"]:
        result["reason"] = "no_socket"
        return result
    try:
        with docker_client() as client:
            # A ping first, so a socket the process may not open gets its
            # own name: the app runs as uid 1000 and a root-owned socket
            # denies it, which used to surface as "container not found".
            try:
                client.get("/_ping").raise_for_status()
            except httpx.ConnectError as exc:
                if "permission" in str(exc).lower():
                    logger.info("Docker socket present but not permitted: %s", exc)
                    result["reason"] = "socket_permission"
                    return result
                raise
            container_id = own_container_id(client)
            if container_id is None:
                result["reason"] = "container_not_found"
                return result
            inspect = client.get(f"/containers/{container_id}/json")
            inspect.raise_for_status()
            image = str(inspect.json()["Config"]["Image"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.info("Docker socket present but not usable: %s", exc)
        result["reason"] = "socket_unusable"
        return result
    result["container"] = container_id
    result["image"] = image
    repo = image.rsplit(":", 1)[0] if ":" in image.rsplit("/", 1)[-1] else image
    if repo != IMAGE_REPOSITORY:
        result["reason"] = "foreign_image"
        return result
    result["available"] = True
    return result


def read_state() -> dict[str, Any] | None:
    try:
        return json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_state(state: dict[str, Any]) -> None:
    payload = {**state, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        state_file().write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    except OSError as exc:  # pragma: no cover - full disk
        logger.warning("Could not record update state: %s", exc)


def clear_state() -> None:
    try:
        state_file().unlink(missing_ok=True)
    except OSError:  # pragma: no cover
        pass


def _pull(client: httpx.Client, reference: str) -> None:
    """Pull an image by tag, waiting for the daemon to finish.

    The create endpoint streams progress lines; the pull has only really
    happened when the stream ends without an error line and the image is
    inspectable afterwards.
    """
    repo, tag = reference.rsplit(":", 1)
    with client.stream(
        "POST",
        "/images/create",
        params={"fromImage": repo, "tag": tag},
        timeout=get_settings().update_apply_pull_timeout_seconds,
    ) as response:
        if response.status_code != 200:
            response.read()
            raise UpdateError(
                f"The registry refused the pull of {reference} "
                f"(HTTP {response.status_code}).")
        for line in response.iter_lines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if "error" in event:
                raise UpdateError(
                    f"Pulling {reference} failed: {event['error']}")
    check = client.get(f"/images/{reference}/json")
    if check.status_code != 200:
        raise UpdateError(
            f"The daemon reports no image {reference} after the pull.")


def _bind_destination(bind: str) -> str:
    """The container path a bind mount targets.

    A bind reads ``source:destination`` with optional modes appended —
    Unraid writes the socket as ``/var/run/docker.sock:/var/run/docker.sock:rw``.
    Comparing whole bind strings therefore misses a socket that is already
    mounted, and mounting it a second time makes the daemon refuse the
    container with "Duplicate mount point".
    """
    parts = bind.split(":")
    return parts[1] if len(parts) > 1 else parts[0]


def start_update(target_version: str) -> dict[str, Any]:
    """Pull the release image and hand the swap to the helper container.

    Returns as soon as the helper is running; the caller should tell the
    administrator the application is about to restart, because it is —
    the helper stops this container as its first act.
    """
    ability = capability()
    if not ability["available"]:
        raise UpdateError(f"In-app updating is not available: {ability['reason']}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", target_version or ""):
        raise UpdateError(f"Not a release version: {target_version!r}")

    # The publish workflow tags images with the bare version — docker/metadata
    # -action's semver pattern strips the "v" from the git tag — so the image
    # for release v1.136.0 lives at ...emcargo:1.136.0, not :v1.136.0.
    reference = f"{IMAGE_REPOSITORY}:{target_version}"
    with docker_client() as client:
        write_state({"phase": "pulling", "to": target_version})
        _pull(client, reference)

        inspect = client.get(f"/containers/{ability['container']}/json")
        inspect.raise_for_status()
        own = inspect.json()
        binds = list((own.get("HostConfig") or {}).get("Binds") or [])
        socket_bind = f"{DOCKER_SOCKET}:{DOCKER_SOCKET}"
        if not any(_bind_destination(bind) == str(DOCKER_SOCKET)
                   for bind in binds):
            binds.append(socket_bind)

        helper_name = f"{HELPER_NAME_PREFIX}-{int(time.time())}"
        create = client.post(
            "/containers/create",
            params={"name": helper_name},
            json={
                "Image": reference,
                "Entrypoint": ["python", "-m", "app.update_helper"],
                "Cmd": [own["Id"], reference],
                "HostConfig": {
                    "Binds": binds,
                    "AutoRemove": True,
                    "NetworkMode": "none",
                },
                "Labels": {"io.emcargo.updater": "true"},
            },
        )
        if create.status_code not in (200, 201):
            raise UpdateError(
                "Could not create the updater container: "
                f"HTTP {create.status_code} {create.text[:300]}")
        helper_id = create.json()["Id"]
        start = client.post(f"/containers/{helper_id}/start")
        if start.status_code not in (204, 304):
            raise UpdateError(
                f"Could not start the updater container: HTTP {start.status_code}")

    write_state({"phase": "handed_over", "to": target_version,
                 "helper": helper_name})
    return {"helper": helper_name, "to": target_version}
