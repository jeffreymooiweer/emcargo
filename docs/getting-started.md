# Getting started

EMCargo ships as a single Docker image containing both the backend and the web
interface. There is no separate database to install — it uses a SQLite file on disk. A
host without Docker installs it as a native systemd service, and a cluster runs it from
plain manifests: both in [Installing without Docker](installation-native.md).

- [Docker Compose](#docker-compose)
- [Unraid](#unraid)
- [Without Docker: native service or Kubernetes](installation-native.md)
- [The first admin account](#the-first-admin-account)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)

## Docker Compose

```bash
git clone https://github.com/jeffreymooiweer/emcargo.git
cd emcargo
cp .env.example .env
```

Open `.env` and set one thing:

| Setting | What to put there |
|---|---|
| `ADMIN_PASSWORD` | The password for your first admin account. |

Everything else has a working default, including `APP_SECRET_KEY`: leave it empty and
EMCargo generates a key on first start and keeps it in `DATA_DIR/secret_key`. Set it
yourself only if you want to manage the key — to share it across instances, say:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then start it:

```bash
docker compose up -d --build
```

Open <http://localhost:8080>.

Every other setting has a sensible default. If you want to change one, see
[Configuration](configuration.md).

## Unraid

1. Add the template `unraid/EMCargo.xml`
   manually.
2. Map the volume `/mnt/user/appdata/emcargo` → `/data`.
3. Use the image `ghcr.io/jeffreymooiweer/emcargo:latest`, or pin a specific version such as
   `ghcr.io/jeffreymooiweer/emcargo:2.0.0`.
4. Fill in the `ADMIN_*` variables. `APP_SECRET_KEY` may stay empty — it is generated on
   first start and kept in `/data/secret_key`.
5. Pick a WebUI port, for example `http://<server-ip>:9935`.

**File permissions.** On startup the container sets the owner of `/data` to `PUID`/`PGID`
(both default to `1000`). If your Unraid share uses different IDs, set them as
environment variables.

## The first admin account

There is no public sign-up page. The first administrator is created on first startup,
and only if all three of these are set:

- `ADMIN_USERNAME`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

Log in with those credentials. You can create more users from inside the app afterwards.
Under **Settings** an administrator sets what those new users start with — language, theme
and the organisation name offered as their consignor.

If you forget the password, use **Forgot password?** when outgoing mail is configured,
or ask an existing administrator to reset the account. Changing the bootstrap password
does not reset an existing account. Preserve the database and make a backup before any
manual recovery; deleting it also deletes accounts and application data.

## Updating

```bash
docker compose pull
docker compose up -d
```

On Unraid, click **Check for updates** or use the Docker tab as usual. A native install
updates with its update script and a Kubernetes install with a rollout; see
[Installing without Docker](installation-native.md#native-service).

Your data lives in the `/data` volume and survives updates. New reference data (goods,
locations, UN numbers) is picked up automatically the next time the catalogue syncs,
which happens at startup.

EMCargo images are published exclusively to GHCR. When upgrading an existing
installation, keep its existing host data directory and volume mapping.

## Troubleshooting

**The container starts and immediately stops, and the log window closes before I can
read it.**
That is a known defect in **v1.25.0 up to and including v1.29.2**. Those versions refused
to start when `APP_SECRET_KEY` was empty or still on its default and when
`CORS_ALLOWED_ORIGINS` was `*` — which is exactly what they shipped with, and what the
Unraid template passes through. The container exited before anything could be read.

Update to **v1.29.3 or newer**; it generates a key for itself and starts. If you cannot
update yet, set `APP_SECRET_KEY` to a long random value of your own and add
`CORS_ALLOWED_ORIGINS` with the address you reach EMCargo on, and the older version
starts too.

**The page loads but I cannot log in.**
The admin account is only created when `ADMIN_USERNAME`, `ADMIN_EMAIL` *and*
`ADMIN_PASSWORD` are all present at first startup. Check the container logs — the
bootstrap step reports what it did.

**Startup is slow, or hangs on a network call.**
EMCargo refreshes its reference catalogues from public sources at startup. Switch that
off under **Settings → Outbound connections**, or set `CATALOG_AUTO_SYNC=false`. The
bundled data in the image is used instead, and weight calculations are unaffected. Because
it is only read while the application starts, the setting takes effect on the next restart.

**Address search does not return anything.**
Address autocomplete calls an external geocoder (`photon.komoot.io` by default), so it
needs internet access. Check first whether an administrator has switched it off under
**Settings → Outbound connections** — on an installation that is meant to stay off the
internet that is deliberate. Airport, port and station search works fully offline, and you
can always type an address by hand.

**Permission errors on `/data`.**
Set `PUID` and `PGID` to match the owner of your host folder.
