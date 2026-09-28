let labSetupCaptured = false;
let pageViewCaptured = false;
const CONTROLLED_VERIFICATION_PARAM = 'verification';
const CONTROLLED_VERIFICATION_VALUE = 'controlled';
const VISIT_TYPE_EVENTS = new Set([
    'lab_viewed',
    'reaction_analysis_completed'
]);
export function capture(event, properties = {}) {
    const query = new URLSearchParams(window.location?.search ?? '');
    const isControlledVerification = (query.get(CONTROLLED_VERIFICATION_PARAM) ===
        CONTROLLED_VERIFICATION_VALUE);
    if (isControlledVerification)
        return;
    const tracksVisitType = VISIT_TYPE_EVENTS.has(event);
    const measuredProperties = tracksVisitType
        ? { ...properties, visit_type: 'unclassified' }
        : properties;
    window.posthog?.capture?.(event, {
        ...measuredProperties,
        page_path: normalizedPath(window.location?.pathname),
        controlled_run: false,
    });
}
export function captureLabSetupStarted(properties) {
    if (labSetupCaptured)
        return;
    labSetupCaptured = true;
    capture('lab_setup_started', properties);
}
/** Paths never include search strings, fragments, or encoded private input. */
export function normalizedPath(path) {
    if (typeof path !== 'string')
        return '/';
    const clean = path.split(/[?#]/, 1)[0] || '/';
    return /^\/(?:[a-z0-9_-]+\/)*[a-z0-9_-]*$/i.test(clean) ? clean : '/unknown/';
}
export function capturePageView() {
    if (pageViewCaptured)
        return;
    pageViewCaptured = true;
    capture('$pageview');
}
//# sourceMappingURL=analytics.js.map