import test from 'node:test';
import assert from 'node:assert/strict';

const capturedEvents = [];

globalThis.window = {
    location: { search: '' },
    posthog: {
        capture(...args) {
            capturedEvents.push(args);
        }
    }
};

const { capture } = await import('../static/js/analytics/analytics.js');

test('an unflagged lab page emits an unclassified lab_viewed event', () => {
    window.location.search = '';
    window.location.pathname = '/demo/sodium-chlorine/';
    const countBeforeCapture = capturedEvents.length;

    capture('lab_viewed', { route: window.location.pathname });

    assert.deepEqual(
        capturedEvents.slice(countBeforeCapture),
        [[
            'lab_viewed',
            {
                route: '/demo/sodium-chlorine/',
                visit_type: 'unclassified',
                page_path: '/demo/sodium-chlorine/',
                controlled_run: false
            }
        ]]
    );
});

test('completed analyses default to unclassified and ignore caller overrides', () => {
    window.location.search = '';
    const countBeforeCapture = capturedEvents.length;

    capture('reaction_analysis_completed', {
        chemical_count: 2,
        visit_type: 'internal'
    });

    assert.deepEqual(
        capturedEvents.slice(countBeforeCapture),
        [[
            'reaction_analysis_completed',
            {
                chemical_count: 2,
                visit_type: 'unclassified',
                page_path: '/demo/sodium-chlorine/',
                controlled_run: false
            }
        ]]
    );
});

test('controlled pages suppress every product analytics event', () => {
    capturedEvents.length = 0;
    window.location.search = '?verification=controlled&source=student_invite';

    capture('lab_viewed', { route: '/demo/sodium-chlorine/' });
    capture('reaction_analysis_started', { chemical_count: 2 });
    capture('reaction_analysis_completed', { chemical_count: 2 });
    capture('reaction_demo_entered', { demo_version: '1' });

    assert.deepEqual(capturedEvents, []);
});

test('non-visit events retain their existing unflagged properties', () => {
    window.location.search = '?verification=unexpected';
    const countBeforeCapture = capturedEvents.length;

    capture('guide_visit', { entry_source: 'bounded_test_value' });

    assert.deepEqual(
        capturedEvents.slice(countBeforeCapture),
        [['guide_visit', { entry_source: 'bounded_test_value', page_path: '/demo/sodium-chlorine/', controlled_run: false }]]
    );
});
