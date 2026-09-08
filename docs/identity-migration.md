# Complete EMCargo identity migration

This change renames technical identifiers as well as the interface. It is not an
automatic migration of an existing installation. Published v2.0.0 artifacts are
unchanged; the renamed native bundle is produced by the next release.

## Existing data

Export browser-only drafts from the old version first. Stop the application and
back up its complete data directory. Use the migration utility to copy that data
and its SQLite database into a **new** directory:

```bash
python3 scripts/migrate_identity.py \
  --source /path/to/existing-data \
  --database existing-database.db \
  --target /path/to/emcargo-data \
  --application-stopped
```

Replace the example source directory and filename with the actual installation
values. The utility refuses an existing destination, checks SQLite integrity,
copies uploads and the secret key, and writes `emcargo.db` using SQLite's backup
API. It does not change the source. Keep the application stopped while copying so
the database and uploads remain consistent. Set filesystem ownership for the
application user before starting it.

Mount the new directory at `/data` and set
`DATABASE_URL=sqlite:////data/emcargo.db`. Alternatively, keep an explicitly
configured existing database URL; the new default must not accidentally select an
empty database. Keep a backup until account, shipment and document access succeeds.

## Configuration and native services

Use `EMCARGO_HISTORY` for the initial retention setting; the previous
product-prefixed variables are no longer read. `EMCARGO_MODE` is retired as of
v2.3.0: all installations require sign-in. Former open installations must set the
`ADMIN_*` variables to create their first administrator. Preserve the existing
data volume and database URL; no data reset is part of this change. Public UN-card
QR links continue to work without an account.

New native installations use `/opt/emcargo`, `/etc/emcargo/emcargo.env`,
`/var/lib/emcargo` and `emcargo.service`. Stop and disable the previous service
before enabling the new one. Migrate its data and configuration first. Do not run
both services against the same database. Keep the former release and data for
rollback; never overwrite them with the new installation.

The renamed installer expects the next release's EMCargo native bundle. For a
local build, pass that bundle with `--bundle`; older published bundles use their
own bundled installer and service layout.

## Browser state and integrations

Browser preference and draft keys now use `emcargo`. Language/theme preferences
may need selecting again. Import exported drafts rather than deleting browser
storage. Existing server-side records remain available in the migrated database.

Structured shipment exports now identify as `emcargo.shipment`, format version
`2.0`. Update consumers to recognize that identifier. Download filenames, event
names, updater labels and generated card archive names also use the EMCargo prefix.
New generated card ZIPs must be published before using the newly named asset feed.
