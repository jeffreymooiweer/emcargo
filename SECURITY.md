# Security policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting instead:

> **[Report a vulnerability](https://github.com/jeffreymooiweer/emcargo/security/advisories/new)**
> — or go to the repository's **Security** tab → *Report a vulnerability*.

That opens a private thread visible only to you and the maintainer.

If private reporting is unavailable to you for any reason, open a public issue saying
only that you have found a security problem and would like a private channel — **without
any detail** — and you will be contacted.

### What to include

- What the problem is, and what an attacker could do with it.
- How to reproduce it: the request, the input, the configuration.
- The version (`GET /api/health` returns it, and it is in `VERSION`).
- How you are running it: Docker image, Unraid, from source.

Proof-of-concept code is welcome. Please do not test against anyone else's installation.

### What to expect

This is a personal project maintained by one person, so please be patient rather than
surprised:

- An acknowledgement within about a week.
- An assessment — whether it is in scope, and how serious — after that.
- A fix released as a normal version, with the problem described in `CHANGELOG.md`.

You will be credited in the changelog unless you would rather not be. There is no bounty
programme.

## Supported versions

| Version | Supported |
|---|---|
| The [latest release](https://github.com/jeffreymooiweer/emcargo/releases/latest) | Yes |
| Anything older | No — upgrade first |

EMCargo is pre-2.0 and under active development. Fixes go into the next release; there
are no backports to older tags.

## What is in scope

EMCargo is **self-hosted**. There is no EMCargo cloud service, no account with us
and no telemetry, so the attack surface is your own deployment. In scope:

- Authentication and session handling, and the admin bootstrap
  (`ADMIN_USERNAME` / `ADMIN_EMAIL` / `ADMIN_PASSWORD`, which creates the first admin on
  startup — there is no public registration).
- Authorisation: one user reaching another user's data.
- Injection of any kind against the API or the SQLite database.
- Anything that lets an uploaded or pasted file — Excel, CSV, a filled PDF template —
  execute code, read files off the host, or escape the container.
- Path traversal in document export or in the UN card downloads.
- `CATALOG_AUTO_SYNC`, which fetches reference catalogues from external URLs at startup:
  anything that turns that into a way to reach the host or poison the data.
- Secrets leaking into logs, exports or error responses.
- Dependencies with a known, exploitable vulnerability reachable from EMCargo.

## What is not in scope

- **Wrong regulatory data or a wrong document.** A mistaken density, class, segregation
  code or form field is a correctness bug, not a vulnerability. Please report those as a
  normal issue — see [CONTRIBUTING.md](CONTRIBUTING.md). They are taken seriously; they
  just do not need a private channel.
- **The documents being drafts.** Every export is a draft that a qualified person must
  check and sign. That is the design, stated in [DISCLAIMER.md](DISCLAIMER.md), and not a
  defect.
- **An installation you exposed to the internet without a reverse proxy, TLS or a
  password.** EMCargo is meant to run on your own machine or a private network.
  Hardening the perimeter is the operator's job.
- Missing hardening headers, rate limits or similar with no demonstrated impact, and
  automated scanner output without a working reproduction.
- Social engineering, physical access, or denial of service by simply sending a lot of
  traffic.

## Handling your data while reporting

Do not attach real shipment data. Redact company names, addresses, reference numbers and
consignee details before sending anything — placeholders make the report no less useful.
