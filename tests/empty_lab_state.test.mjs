import assert from 'node:assert/strict';
import test from 'node:test';

const calls = [];
const ctx = new Proxy({}, {
    get: (_, name) => name === 'createLinearGradient'
        ? () => ({ addColorStop() {} })
        : (...args) => { calls.push([name, ...args]); }
});
const selected = new Set();
const cards = ['flask', 'beaker', 'tube', 'cylinder', 'burner'].map(id => ({
    id: `opt-${id}`,
    classList: {
        add: () => selected.add(id),
        remove: () => selected.delete(id)
    },
    setAttribute() {}
}));
const canvas = {
    width: 800,
    height: 500,
    dataset: {},
    getContext: () => ctx,
    closest: () => workspace
};
const workspace = { classList: { contains: () => false } };
globalThis.window = {
    location: { pathname: '/lab/', search: '?verification=controlled' },
    localStorage: { removeItem() {} },
    matchMedia: () => ({ matches: true }),
    dispatchEvent() {}
};
globalThis.document = {
    addEventListener() {},
    getElementById: id => id === 'lab-canvas' ? canvas : cards.find(card => card.id === id) || null,
    querySelectorAll: selector => selector === '.apparatus-option-card[id^="opt-"]' ? cards : [],
    cookie: ''
};

const config = await import('../static/js/configuration/config.js');
const { drawVesselAndFluid } = await import('../static/js/rendering/render.js');
const { selectVessel } = await import('../static/js/userInterface/ui.js');
const { resetLaboratory } = await import('../static/js/interactions/interactions.js');

test('a normal first load draws no apparatus until the student selects one', () => {
    assert.equal(config.getLabState().apparatusSelected, false);
    drawVesselAndFluid();
    assert.deepEqual(calls.map(call => call[0]), ['clearRect']);

    calls.length = 0;
    selectVessel('flask');
    drawVesselAndFluid();
    assert.equal(config.getLabState().apparatusSelected, true);
    assert.ok(calls.some(call => call[0] === 'stroke'));
    assert.ok(selected.has('flask'));
});

test('reset removes the last apparatus and restores the empty work zone', () => {
    resetLaboratory();
    calls.length = 0;
    drawVesselAndFluid();
    assert.equal(config.getLabState().apparatusSelected, false);
    assert.equal(config.getLabState().burnerActive, false);
    assert.equal(selected.size, 0);
    assert.deepEqual(calls.map(call => call[0]), ['clearRect']);
});

test('panel resize holds the vessel while full close centers it', () => {
    config.updateLabState({ vesselOffsetX: 0 });
    canvas.dataset.expandedAnchorWidth = '800';
    canvas.width = 650;
    assert.equal(config.vesselCenterX(), 400);
    workspace.classList.contains = name => name === 'is-analysis-collapsed';
    canvas.width = 1000;
    assert.equal(config.vesselCenterX(), 500);
});
