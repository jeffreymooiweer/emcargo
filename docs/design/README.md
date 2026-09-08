# EMCargo interface reference

The owner explicitly requested the same interface as these three approved dark
mockups, with the product name changed to **EMCargo**. These are design references,
not screenshots of the implemented application.

- [Desktop overview](reference-dashboard.png)
- [Desktop shipment](reference-shipment.png)
- [Mobile shipment](reference-mobile.png)

The reference defines the navy palette, blue actions, persistent 240px sidebar,
three-stage shipment header, goods cards, summary column and bottom action bar.
The mobile composition uses a compact top bar, three progress segments, stacked
cards and accessible primary actions.

## Functional constraints

- Real data drives every count. The illustrative mockup statuses and recognition
  percentages are not evidence of regulatory approval or measured AI accuracy.
- Dangerous-goods assessment remains a required part of the goods stage. Grouping
  progress into three stages does not skip underlying checks.
- Open installations remain anonymous and do not gain server-side history.
- Existing custom branding and explicit light/system preferences survive.
- CargoPilot database paths, browser keys, JSON format identifiers, native service
  names and native bundle filenames are compatibility identifiers. LICENSE remains
  unchanged. Updates and container images use this repository, never the upstream.

## Verification in this change

The frontend production build passed. All 343 frontend tests passed, followed by
62 affected UI tests after the final table and row-layout changes. The final full
backend run passed 2,653 tests and skipped three. Its six failures were version
metadata checks caused by `backend/VERSION` lagging the other version files;
these were corrected with the repository's version-bump script and rechecked.
The earlier 194 affected branding, settings, export and installation tests passed.

No production data or upstream CargoPilot repository was modified. No release has
been deployed. Docker publication and visual browser verification are not claimed.

Visual browser verification remains outstanding: both the initial browser
connection and the supervised preview returned `ERR_BLOCKED_BY_CLIENT`. The
reference images have been retained so desktop and mobile screenshots can be
compared against them in a working browser environment. Do not describe this
implementation as pixel-perfect or browser-verified until that comparison is done.
