# Public-page tracking verification

## Capture contract

Every public HTML route loads one explicit `$pageview` per document load.
Lab and guide activity events remain separate from pageviews. APIs, health,
robots, sitemap, static files and staff admin do not count as public pages.
All activity receives `page_path`, without queries or fragments. Unsupported
path characters become `/unknown/`. No page copy changes.

PostHog's existing SDK owns identity. `visitor_id` aliases `distinct_id` and
`session_id` aliases `$session_id` after SDK enrichment. No parallel identity
system, account identity, or fingerprinting is added. Local storage persists
browser identity until cleared. Without working storage, SDK memory persistence
keeps the current page usable but cannot deduplicate later page loads.
Sessions renew after 30 inactive minutes or the SDK's 24-hour maximum.
These count browser identities, not unique people or cross-device visitors.

First arrival uses SDK-session-keyed local storage, with a page-memory fallback.
It carries the landing path, referring origin and bounded source/medium/campaign
labels. Empty referrer means `direct`; malformed referrer means `unknown`.
A tagged URL can still have a direct referrer classification. Internal navigation
retains the first arrival until SDK session renewal. Invalid campaign values
become empty strings. Accept only 1-64 letter/digit/underscore/hyphen labels,
starting with a letter. Email addresses and URL values are rejected.

The final SDK `before_send` allowlist removes automatic full URLs, referrers,
initial-person properties, titles and unapproved fields. SDK campaign/referrer
persistence is disabled. Existing source labels remain. Controlled URLs suppress
both SDK initialization and all product captures. Non-public hosts and noindex
sites still omit SDK initialization. `controlled_run` is false on eligible events;
controlled=true events are intentionally never sent.

## Browser proof, September 15, 2026

One marked internal guide-to-demo journey ran at 13:41 UTC in workspace Chrome.
The real PostHog web SDK version 1.433.4 used a test-only token and local sink.
The test harness supplied the SDK on preview; shipped preview behavior remains off.
The sink recorded final sanitized payloads and returned null before transport.
PostHog domains were also blocked in the browser debugging connection.
No actual provider delivery is claimed.

The guide link selected sodium and chlorine. Changing the vessel fired setup.
Analysis produced `2Na(s) + Cl2(g) -> 2NaCl(s)` and all three safety rules.
The educational boundary stayed present. No feedback form was submitted.

| Event | Path | Expected fields present |
|---|---|---|
| $pageview | /guides/sodium-and-chlorine-reaction/ | 11/11 |
| chemistry_guide_entered | /guides/sodium-and-chlorine-reaction/ | 11/11 |
| $pageview | /demo/sodium-chlorine/ | 11/11 |
| lab_viewed | /demo/sodium-chlorine/ | 11/11 |
| reaction_demo_entered | /demo/sodium-chlorine/ | 11/11 |
| lab_setup_started | /demo/sodium-chlorine/ | 11/11 |
| reaction_analysis_started | /demo/sodium-chlorine/ | 11/11 |
| reaction_analysis_completed | /demo/sodium-chlorine/ | 11/11 |
| reaction_feedback_prompt_viewed | /demo/sodium-chlorine/ | 11/11 |

All 11 expected fields appeared on each event. Both pages shared one SDK browser
identifier and one SDK session identifier. `utm_source=reddit`, `utm_medium=forum`
and `utm_campaign=cycle40` persisted to the result. These are test labels, not
proof of a real Reddit visit. Referrer origin was empty for this direct test.
Unit tests cover referral origins, internal navigation and malformed values.
Exactly two pageviews represented the two document loads.

Separate isolated SDK checks advanced the browser clock 31 minutes. The session
changed and browser identity stayed constant. SDK reset changed browser identity.
Blocking local storage chose memory persistence and still produced one pageview.
The lab was reset and all test storage cleared. A final controlled preview had
zero local/session keys and no PostHog instance.

## Delivery and reporting limits

- Browser capture: verified, including final SDK-enriched fields.
- Outbound production transport: intentionally suppressed by the test sink.
- Provider receipt: unverified; the isolated run sent no production events.
- Readable reporting: current SQLite schema has aggregate `metric_points` and
  summary-only `integration_events`, with no raw PostHog event property table.
  Latest inspected slices contain event names, not paths or browser identities.
  Both PostHog collectors last succeeded around 10:51 UTC on September 15.
  Code cannot backfill old events or expand the platform's reporting surface.

## Checks

225 Django tests, 47 JavaScript tests and TypeScript checks pass.
The route test enumerates current public URL patterns and checks one pageview
entry and one production SDK hook each. It checks SDK exclusion on localhost.
Unit tests cover duplicate prevention, sanitization, attribution and exclusions.

## SDK references

- https://posthog.com/docs/libraries/js/persistence
- https://posthog.com/docs/data/sessions

## Undo

Revert this isolated tracking change. Existing historical provider events cannot
be retroactively removed by a code revert. No provider events were sent by the test.
