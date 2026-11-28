import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.document = { getElementById: () => null };
globalThis.window = {
    supportedReactionPairs: [['HCl', 'NaOH'], ['Na', 'Cl2']],
    location: { pathname: '/lab/' }
};

const { transferHalf, totalPortions } = await import('../static/js/interactions/twoVessels.js');

function setup(first, second = {}, secondVisible = true) {
    return { first, second, secondVisible, secondColor: '#2b9ed8', firstType: 'beaker' };
}

test('transfer conserves every chemical and permits a supported pair', () => {
    const before = setup({ HCl: 30 }, { NaOH: 30 });
    const after = transferHalf(before, 'first');
    assert.ok(after);
    assert.equal(after.first.HCl, 15);
    assert.equal(after.second.HCl, 15);
    assert.equal(after.second.NaOH, 30);
    for (const id of ['HCl', 'NaOH']) {
        assert.equal((before.first[id] || 0) + (before.second[id] || 0),
            (after.first[id] || 0) + (after.second[id] || 0));
    }
    assert.equal(totalPortions(after.first) + totalPortions(after.second), 60);
});

test('transfer works in both directions and never moves more than the source has', () => {
    const firstMove = transferHalf(setup({}, { HCl: 1 }), 'second');
    assert.ok(firstMove);
    assert.equal(firstMove.first.HCl, 1);
    assert.equal(firstMove.second.HCl, 0);
    assert.equal(transferHalf(firstMove, 'second'), null);
});

test('empty, unsupported, over-capacity and missing second vessel are blocked', () => {
    assert.equal(transferHalf(setup({}, {}), 'first'), null);
    assert.equal(transferHalf(setup({ HCl: 30 }, { Na: 30 }), 'first'), null);
    assert.equal(transferHalf(setup({ HCl: 30 }, { HCl: 205 }), 'first'), null);
    assert.equal(transferHalf(setup({ HCl: 30 }, {}, false), 'first'), null);
});
