# Installing without Docker

## Native service

Use the installer from this repository. It downloads the native bundle attached to
an EMCargo release and installs the backend, built frontend and document templates.
The archive name, service identifier and native filesystem paths retain their
historical compatibility names; use the paths reported by the installer instead of
renaming an existing installation manually.

Requirements: Linux with systemd, Python 3.12 with venv, curl, tar and root access.

```bash
curl -fsSL https://raw.githubusercontent.com/jeffreymooiweer/emcargo/main/deploy/native/install.sh -o install.sh
sudo bash install.sh 2.0.0
```

Set `ADMIN_PASSWORD`, `PUBLIC_URL` and `CORS_ALLOWED_ORIGINS` in the generated
environment file before exposing the service. The backend listens on
`127.0.0.1:8080`; terminate HTTPS at your reverse proxy.

For updates, run `deploy/native/update.sh` from the current installed release as
root, optionally passing the release version. Keep the existing data directory,
service identity and environment file. Back up the data directory before updating.
The in-app Docker updater does not apply to native installations.

See [the installer](../deploy/native/install.sh),
[the updater](../deploy/native/update.sh) and [configuration](configuration.md).

## Kubernetes

The manifest for new installations is [emcargo.yaml](../deploy/kubernetes/emcargo.yaml).
Set the administrator password, ingress hostname, TLS and storage size first.

```bash
kubectl apply -f deploy/kubernetes/emcargo.yaml
kubectl -n emcargo set image deployment/emcargo emcargo=ghcr.io/jeffreymooiweer/emcargo:2.0.0
```

Use one replica and the `Recreate` strategy because the application uses SQLite.
For an existing cluster, update its current deployment and preserve its namespace
and persistent volume claim. Applying the renamed manifest alongside it creates
separate resources; it does not migrate the database.

## Persistent data

Keep the complete `DATA_DIR`, including the database, uploads, branding, UN cards
and secret key. The `ADMIN_*` variables bootstrap the first account only. Existing
accounts are managed in the application. Shipment history is configured under
**Settings → Administration → Keep shipments**.
