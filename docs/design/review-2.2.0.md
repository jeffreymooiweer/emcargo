# EMCargo 2.2.0 experience review

Review date: 8 September 2026. Based on EMCargo 2.1.1, commit
`ce4891cfc13a715e958c4de5fbd9503dec0530d4`. This change implements the requested
app-wide design review and restoration of discoverable in-app updates.

## Design decisions

The application uses an ink-navy navigation rail, neutral content surfaces and
cobalt actions. The new E/forward mark is an original scalable SVG. Interface
icons share a 24px grid and one stroke weight; transport, documents, security,
import, signing and destructive actions have distinct meanings. Official
regulatory label artwork is unchanged.

Seven original image-generator photographs form one transport series. Four
available transport modes receive photographic cards. Air and multimodal
remain unavailable, with their explanations and preview images in a secondary
disclosure. The login/reset layout uses the harbour photograph at desktop
widths; the phone prioritizes the form. Custom user branding still overrides
default images. [The asset manifest](art-2.2.0.json) records the actual prompts
and delivered file sizes; the seven WebP files total roughly 1.6 MB.

Settings now have named destinations grouped into personal, organisation and
system tasks. In particular, mail no longer contains the two-factor policy or
QR-card controls. Security contains personal 2FA plus the administrator's
installation policy and session duration. Connections contains the public
installation address. UN cards contains sharing options and installed-card
management. The Updates destination combines discovery, capability, manual
checking, confirmation and progress. Mobile uses a section selector.

The dangerous-goods step starts with identity and currently unanswered
questions. Derived classification details and special cases remain accessible
without competing with the required answers. An unselected closed-answer
field now displays a blank choice instead of implying that the first option
was already answered. Stale derived results are cleared while preparing new
input; calculation, classification and document rules have not been changed.

The export page presents a review grid, collapsible weight corrections, the
compliance findings and the document workspace. Repeated document warnings are
grouped once with every affected document retained. Warning text remains
visible. Failed checks say they are unavailable; missing-field links and
export blockers remain at their document. History and supplementary reference
material follow the primary work.

Library and user creation forms open on demand, including automatically when
an item is edited. Equipment fields have persistent labels. Collection pages
share typography, spacing, readable table rows and aligned filters.
Notifications use neutral surfaces with colour on their icon/border. Timed
notifications pause on pointer interaction or keyboard focus; persistent
errors and the deferred undo contract remain intact. Confirmations trap focus
and restore it on dismissal. Reduced-motion preferences suppress decorative
motion.

## Verification

- Production TypeScript/Vite build passed. The existing Vite chunk-size warning
  remains; no new runtime package was added.
- Complete frontend suite: **380 tests passed**. This includes new checks for
  update capability, unreachable releases, resumed polling, navigation cleanup,
  concurrent confirmation, failed updates, preserving instance settings, paused
  undo and loading outcomes, warning deduplication and clearing stale document findings.
- Backend update/check/settings/language/error selection: **146 tests passed**
  in the first integration pass. After the final updater changes, the focused
  updater/error/language selection passed **115 tests**, including named-mount
  preservation, custom DATA_DIR, handover ordering, digest identity, Docker
  health and duplicate-apply regressions. These selections overlap; their
  counts should not be added together.
- Version consistency and whitespace checks passed.
- Real browser review used the Vite development preview with the repository's
  opt-in review bridge and a real FastAPI TestClient against temporary synthetic
  data. It did not access a production installation. Desktop and 355/390px
  iframe layouts were inspected. They are CSS viewport checks, not claims of
  physical-device testing or accessibility certification.
- Reviewed dashboard, transport choice, goods, dangerous goods, shipment
  details, export, shipment list, empty trips, groupage, articles, equipment,
  users, audit, annual report, all settings destinations, legal and public-card
  views, plus login/reset presentation. The DG walkthrough confirmed UN 1203,
  exercised name choices and quantities, and verified that incomplete documents
  retain their missing-data notice on export.

## Practical limits

The Docker replacement was exercised against a scripted Docker API, including
startup rollback and health states. There is no live Unraid host in this
workspace. The repository does not silently enable Docker host access. Existing
installations need the documented socket and opt-in once; native/Kubernetes
installations keep their own deployment route. This PR itself does not publish
a release or update a running installation.

The full backend suite and Docker image build remain CI gates. No regulatory
revalidation is claimed: this release changes presentation and update
orchestration, not the reference tables or calculation algorithms. Long
regulatory findings are still deliberately readable rather than hidden just
to make the page shorter.

Screenshots in `2.2.0/` are actual browser captures from the review; the image
manifest is generation provenance rather than a mockup specification.
