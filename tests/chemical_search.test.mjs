import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.document = { getElementById: () => null };
globalThis.window = { reactionDemo: null, supportedReactionPairs: [] };
const { setupSearchFunction } = await import('../static/js/userInterface/ui.js');

test('chemical search follows replacement and clearing without keyboard events', () => {
    const listeners = new Map();
    const input = {
        value: '',
        addEventListener: (type, handler) => listeners.set(type, handler),
    };
    const cards = [['Zn', 'Zinc'], ['O2', 'Oxygen'], ['Na', 'Sodium']].map(([id, name]) => ({
        getAttribute: () => id,
        textContent: name,
        style: {},
    }));
    const previousDocument = globalThis.document;
    globalThis.document = {
        getElementById: () => input,
        querySelectorAll: () => cards,
    };
    try {
        setupSearchFunction();
        const edit = value => {
            input.value = value;
            listeners.get('input')?.call(input, { type: 'input' });
            return cards.filter(card => card.style.display !== 'none').map(card => card.textContent);
        };
        assert.deepEqual(edit('zinc'), ['Zinc']);
        assert.deepEqual(edit(' oxygen '), ['Oxygen']);
        assert.deepEqual(edit('O2'), ['Oxygen']);
        assert.deepEqual(edit('no match'), []);
        assert.deepEqual(edit(''), ['Zinc', 'Oxygen', 'Sodium']);
    } finally {
        globalThis.document = previousDocument;
    }
});
