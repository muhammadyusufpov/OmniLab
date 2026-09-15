import test from 'node:test';
import assert from 'node:assert/strict';

const capturedEvents = [];

globalThis.document = {
    body: {
        dataset: {
            feedbackEvent: ''
        }
    }
};
globalThis.window = {
    posthog: {
        capture(...args) {
            capturedEvents.push(args);
        }
    }
};

test('focused feedback events fire once with only bounded page properties', async () => {
    const {
        bindFeedbackOpenCapture,
        captureFeedbackPromptViewed
    } = await import(
        '../static/js/interactions/feedback.js'
    );
    const feedbackLink = { onclick: null };
    captureFeedbackPromptViewed(feedbackLink);
    captureFeedbackPromptViewed(feedbackLink);
    bindFeedbackOpenCapture(feedbackLink);
    bindFeedbackOpenCapture(feedbackLink);
    feedbackLink.onclick();

    const expectedRouteEvents = [
        'reaction_feedback_viewed',
        'reaction_feedback_accepted',
        'reaction_feedback_validation_failed',
        'reaction_feedback_rate_limited',
        'reaction_feedback_delivery_failed'
    ];

    for (const event of expectedRouteEvents) {
        document.body.dataset.feedbackEvent = event;
        await import(`../static/js/root/feedback.js?event=${event}`);
    }

    const expectedEvents = [
        'reaction_feedback_prompt_viewed',
        'reaction_feedback_opened',
        ...expectedRouteEvents
    ];
    assert.deepEqual(
        capturedEvents,
        expectedEvents.map(event => [event, {page_path: '/', controlled_run: false}])
    );
});

test('unknown feedback events are ignored', async () => {
    const countBeforeImport = capturedEvents.length;
    document.body.dataset.feedbackEvent = 'private_contact_value';

    await import('../static/js/root/feedback.js?event=unknown');

    assert.equal(capturedEvents.length, countBeforeImport);
});
