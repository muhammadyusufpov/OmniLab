import { normalizedPath } from './analytics.js';

type Properties = Record<string, unknown>;
interface EventPayload { event: string; properties: Properties; [key: string]: unknown; }
const ARRIVAL_KEY = 'omnilab_arrival_v1';
let cachedSession: string | undefined;
let cachedArrival: Properties;
const allowed = new Set([
    'token', 'distinct_id', '$device_id', '$session_id', '$window_id', '$lib', '$lib_version',
    '$insert_id', '$process_person_profile',
    'page_path', 'route', 'controlled_run', 'visit_type', 'visit_source', 'entry_source',
    'prepared_reaction_id', 'demo_version', 'chemical_count', 'vessel', 'burner_active',
    'effect', 'duration_ms', 'stage',
]);

function origin(value: string): string {
    try {
        const url = new URL(value);
        return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url.origin : '';
    } catch { return ''; }
}

function campaign(value: string | null): string {
    // Placement labels only. Reject email addresses, encoded URLs and free text.
    return value && /^[a-z][a-z0-9_-]{0,63}$/i.test(value) ? value : '';
}

function freshArrival(): Properties {
    const query = new URLSearchParams(window.location.search);
    const rawReferrer = document.referrer;
    const referrer = origin(rawReferrer);
    const pageOrigin = origin(window.location.origin);
    return {
        landing_path: normalizedPath(window.location.pathname),
        referrer_origin: referrer,
        arrival_type: !rawReferrer ? 'direct' : !referrer ? 'unknown' :
            referrer === pageOrigin ? 'internal' : 'referral',
        utm_source: campaign(query.get('utm_source')),
        utm_medium: campaign(query.get('utm_medium')),
        utm_campaign: campaign(query.get('utm_campaign')),
    };
}

function arrival(session: string | undefined): Properties {
    if (cachedArrival && cachedSession === session) return cachedArrival;
    let saved;
    try { saved = JSON.parse(window.localStorage.getItem(ARRIVAL_KEY) || 'null'); } catch { /* memory fallback */ }
    cachedSession = session;
    // Revalidate persisted data before reuse; only the current SDK session owns it.
    const a = saved?.arrival;
    cachedArrival = session && saved?.session === session && a &&
        a.landing_path === normalizedPath(a.landing_path) &&
        typeof a.referrer_origin === 'string' && a.referrer_origin === origin(a.referrer_origin) &&
        ['direct', 'unknown', 'internal', 'referral'].includes(a.arrival_type) &&
        ['utm_source', 'utm_medium', 'utm_campaign'].every(k =>
            typeof a[k] === 'string' && (a[k] === '' || a[k] === campaign(a[k])))
        ? Object.fromEntries(['landing_path', 'referrer_origin', 'arrival_type',
            'utm_source', 'utm_medium', 'utm_campaign'].map(k => [k, a[k]]))
        : freshArrival();
    try { window.localStorage.setItem(ARRIVAL_KEY, JSON.stringify({session, arrival: cachedArrival})); }
    catch { /* No storage must never break the lab. */ }
    return cachedArrival;
}

/** Runs after SDK enrichment, immediately before transport. Never persist raw URLs. */
export function sanitizePayload(event: EventPayload | null): EventPayload | null {
    if (!event || new URLSearchParams(window.location.search).get('verification') === 'controlled') return null;
    if (event.event !== '$pageview' && !/^(lab_|reaction_|chemistry_guide_)/.test(event.event)) return null;
    const props = event.properties;
    const safe = Object.fromEntries(Object.entries(props).filter(([key]) => allowed.has(key)));
    const session = typeof props.$session_id === 'string' ? props.$session_id : undefined;
    return { ...event, properties: {
        ...safe,
        page_path: normalizedPath(window.location.pathname),
        ...(safe.route !== undefined ? {route: normalizedPath(safe.route)} : {}),
        page_origin: origin(window.location.origin),
        controlled_run: false,
        // Alias the SDK's own random identifiers; never create a competing identity.
        visitor_id: props.distinct_id,
        session_id: session,
        ...arrival(session),
    }};
}

export function analyticsPersistence(): 'localStorage' | 'memory' {
    try {
        const key = 'omnilab_storage_probe';
        window.localStorage.setItem(key, '1');
        window.localStorage.removeItem(key);
        return 'localStorage';
    } catch { return 'memory'; }
}
