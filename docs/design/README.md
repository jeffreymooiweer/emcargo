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
- EMCargo database paths, browser keys, JSON format identifiers, native service
  names and native bundle filenames are compatibility identifiers. LICENSE remains
  unchanged. Updates and container images use this repository, never the upstream.

## Verification

The EMCargo 2.0 interface passed backend and frontend automation and the production
build. This documentation update additionally tests the new environment aliases,
open-mode behaviour, settings and installation manifests.

The preview now opens the EMCargo sign-in screen in the cloud browser after
explicitly configuring the preview host in Vite and restarting the preview.
This confirms browser connectivity and initial rendering, not authenticated
workflow verification or pixel-perfect agreement with the three references.
Screenshot capture timed out, so no implementation screenshot is claimed here.
