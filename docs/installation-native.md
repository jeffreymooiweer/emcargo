# Installing without Docker

EMCargo ships as a Docker image, and that stays the first-class way in: it is what
every release is built and tested for. Two other routes exist for hosts that do not run
Docker — a **native service** under systemd, and **Kubernetes** — and this page walks
through both. Each has its own way of updating, and the settings screen names the one
that applies instead of offering the in-app update button, which needs a Docker socket.

- [Native service (Debian, Ubuntu and the like)](#native-service)
- [Kubernetes](#kubernetes)
- [What is the same everywhere](#what-is-the-same-everywhere)

## Native service

Every release from v1.181.0 carries a **native bundle**, `cargopilot-<version>-native.tar.gz`,
beside its notes on the GitHub release: the backend, the built web interface, the document
templates, the changelog and the deploy files — the same tree the image carries. The
install script downloads it and does the rest.

**Needs:** a Linux host with systemd, Python 3.11 or newer with the `venv` module
(`apt install python3 python3-venv` on Debian and Ubuntu), `curl` and `tar`, and root for
the installation itself. No Node, no compiler: the interface is built into the bundle
and the Python dependencies come as wheels.

**Install:**

```bash
curl -fsSL https://raw.githubusercontent.com/jeffreymooiweer/emcargo/main/deploy/native/install.sh -o install.sh
sudo bash install.sh            # the latest release
sudo bash install.sh 1.181.0    # or a named one
```

The script creates the service user `cargopilot`, unpacks the release under
`/opt/cargopilot/releases/<version>` with `/opt/cargopilot/current` pointing at it, makes a
virtual environment in `/opt/cargopilot/venv`, writes `/etc/cargopilot/cargopilot.env` from
the example if there is none yet, installs the unit `cargopilot.service` and starts it.
The data — database, uploads, branding, UN cards — lives in `/var/lib/cargopilot`.

Before the first sign-in, open `/etc/cargopilot/cargopilot.env`, set `ADMIN_PASSWORD` and
the address you reach the installation on (`PUBLIC_URL`, `CORS_ALLOWED_ORIGINS`), then
`sudo systemctl restart cargopilot`. Every other variable is in
[Configuration](configuration.md); the unit sets `INSTALL_METHOD=native` so the settings
screen knows which update route to describe.

The service listens on `127.0.0.1:8080` only. Put a reverse proxy with TLS in front of it
— Caddy in two lines:

```
cargopilot.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

or nginx with `proxy_pass http://127.0.0.1:8080;` and the usual `X-Forwarded-*` headers.
`TRUSTED_PROXY_COUNT=1` in the environment file matches one proxy in front.

**Update:**

```bash
sudo /opt/cargopilot/current/deploy/native/update.sh          # the latest release
sudo /opt/cargopilot/current/deploy/native/update.sh 1.182.0  # or a named one
```

The new release is unpacked next to the old one, the `current` link moves, the service
restarts. Nothing under `/var/lib/cargopilot` is touched. To roll back, point the link at
the previous release and restart:

```bash
sudo ln -sfn /opt/cargopilot/releases/1.181.0 /opt/cargopilot/current
sudo systemctl restart cargopilot
```

**Logs:** `journalctl -u cargopilot -f`. **Files:** the unit at
`/etc/systemd/system/cargopilot.service` is a copy of `deploy/native/cargopilot.service`
in the bundle; local changes to it survive an update (the script installs the unit again
only when the file in the bundle changed — compare and merge by hand if you edited it).

**What does not apply here.** The in-app updater (`UPDATE_APPLY_ENABLED`) replaces a
container through the Docker socket and does nothing on a native install; the settings
screen shows the update command above instead. `PUID`/`PGID` are container concerns; the
service runs as its own user.

## Kubernetes

`deploy/kubernetes/cargopilot.yaml` is one file of plain manifests: a namespace, a
persistent volume claim for `/data`, a secret for the first administrator's password, a
config map for the rest of the environment, a deployment of **one** replica, a service,
and an ingress to fill in with your host name and TLS.

```bash
# Edit the host name, the ADMIN_PASSWORD in the secret and the storage size first.
kubectl apply -f deploy/kubernetes/cargopilot.yaml
```

One replica on purpose: the application keeps a SQLite database in `/data` and takes a
file lock on it; two pods on one volume would corrupt it. The deployment's strategy is
`Recreate` for the same reason.

**Update** is a rollout to the newer image tag; the pod is recreated and the volume stays:

```bash
kubectl -n cargopilot set image deployment/cargopilot cargopilot=ghcr.io/jeffreymooiweer/emcargo:1.182.0
```

The config map sets `INSTALL_METHOD=kubernetes`, so the settings screen shows that
command rather than the in-app update button.

## What is the same everywhere

The application is the same in all three routes and reads the same variables. The data
directory (`DATA_DIR`, `/data` in the image and the pod, `/var/lib/cargopilot` natively)
holds everything persistent — see [Privacy](privacy.md#what-is-stored) — and a backup is a
copy of that directory. The first administrator comes from the `ADMIN_*` variables on the
first start; the UN cards are imported once under **Settings → UN cards** and survive
updates in the data directory; the shipment history is switched on by an administrator
under **Settings → Administration → Keep shipments**, on every route alike.
