# In-app updates

Administrators use **Settings → Updates** to see the running version, check
for a release, read the release notes and install it where the installation
supports this. The update notification opens this same page. The legacy
`/settings?tab=maintenance` link redirects to this section.

## Docker Compose

The application must use the official image and have both the explicit opt-in
and access to the Docker socket. Socket access grants control of the Docker
host; enable it only for a trusted installation. The base Compose file keeps
this optional.

From the existing project directory, enable the provided override:

```bash
docker compose -f docker-compose.yml -f docker-compose.updates.yml up -d
```

The override sets `UPDATE_APPLY_ENABLED=true` and mounts
`/var/run/docker.sock:/var/run/docker.sock`. The standard image entrypoint
adds its application user to the socket's group; it does not change host
socket permissions. Installations overriding the image user or entrypoint
must provide the appropriate group access themselves.

The separate **Check for updates** switch controls release-feed requests.
If it is off, neither passive nor manual checks contact GitHub. Turning it
on does not itself authorize installation or grant Docker access.

## Unraid

Edit the existing EMCargo container template and show advanced settings.
Set **In-app updates** (`UPDATE_APPLY_ENABLED`) to `true`. Set the host path
of **Docker socket (optional)** to `/var/run/docker.sock`, keeping its container
path `/var/run/docker.sock`. Apply the template and let Unraid recreate the
container. Previously installed templates may need these entries added once;
a repository template change cannot edit a running Unraid host.

Open **Settings → Updates**. The capability result explains a missing switch,
socket, permission, container identity or official image separately. Once it
reports ready and a newer release is available, the installation button is
enabled. Confirming it starts the pull and restart.

## Progress and recovery

A short-lived helper from the new image replaces the application container.
Its progress is written atomically to `DATA_DIR/update-state.json`; the page
can resume observing it after navigation or a server restart. Bind mounts and
Docker `HostConfig.Mounts` are passed to the helper, including a custom data
path, without adding the socket twice. A configured Docker health check must
be healthy before the previous container is removed. Startup failure invokes
the existing container rollback; failure details remain on the Updates page.

Maintain ordinary data backups. A container rollback is not a database backup
or a general migration rollback. Complex network or container configurations
should continue to use their operator-managed update procedure. Native and
Kubernetes installations display their own update command instead of offering
an impossible Docker replacement.

This change does not install or publish a release by itself. The release must
first exist in GitHub and the corresponding official GHCR image must be
published. The 2.2.0 implementation was tested against a simulated Docker API;
a real Unraid/Docker daemon replacement was not performed in the development
workspace.

Docker request shapes follow the [Docker Engine API reference](https://docs.docker.com/reference/api/engine/version/v1.45/).
