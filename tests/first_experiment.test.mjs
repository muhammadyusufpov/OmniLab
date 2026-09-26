import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = {
    firstExperiment: true,
    supportedReactionPairs: [['Na', 'Cl2']]
};
globalThis.document = {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => []
};

const {
    advanceFirstExperimentGuide,
    focusFirstExperimentTarget,
    getFirstExperimentInstruction,
    getFirstExperimentStep
} = await import(
    '../static/js/firstExperiment/firstExperiment.js'
);
const { updateLabState } = await import(
    '../static/js/configuration/config.js'
);

test('the first experiment starts by asking for Sodium', () => {
    assert.equal(getFirstExperimentStep([], 'flask', false), 'sodium');
});

test('the first experiment asks for Chlorine after Sodium', () => {
    assert.equal(getFirstExperimentStep(['Na'], 'flask', false), 'chlorine');
});

test('the first experiment asks for a beaker after the pair is selected', () => {
    assert.equal(
        getFirstExperimentStep(['Na', 'Cl2'], 'flask', false),
        'beaker'
    );
});

test('the first experiment unlocks analysis after the beaker is selected', () => {
    assert.equal(
        getFirstExperimentStep(['Na', 'Cl2'], 'beaker', false),
        'analyze'
    );
});

test('the first experiment finishes only after a complete result is visible', () => {
    assert.equal(
        getFirstExperimentStep(['Na', 'Cl2'], 'beaker', true),
        'complete'
    );
});

test('visible controls replace the repeated prompts after the first step', () => {
    assert.match(getFirstExperimentInstruction('sodium'), /select Sodium/);
    assert.equal(getFirstExperimentInstruction('chlorine'), null);
    assert.equal(getFirstExperimentInstruction('beaker'), null);
    assert.equal(getFirstExperimentInstruction('analyze'), null);
    assert.match(
        getFirstExperimentInstruction('complete'),
        /does not replace a physical lab procedure/
    );
});

test('the first experiment focuses the next useful closed-panel control', () => {
    const focused = [];
    const elements = {
        'trigger-chemicals': { focus: () => focused.push('trigger-chemicals') },
        'sub-panel-chemicals': { style: { display: 'none' } },
        'trigger-apparatus': { focus: () => focused.push('trigger-apparatus') },
        'sub-panel-apparatus': { style: { display: 'none' } },
        'btn-fire-analysis': { focus: () => focused.push('btn-fire-analysis') }
    };
    globalThis.document.getElementById = id => elements[id] || null;

    focusFirstExperimentTarget('chlorine');
    focusFirstExperimentTarget('beaker');
    focusFirstExperimentTarget('analyze');
    focusFirstExperimentTarget('complete');

    assert.deepEqual(focused, [
        'trigger-chemicals',
        'trigger-apparatus',
        'btn-fire-analysis'
    ]);
});

test('advancing exposes and focuses the next chemical control', () => {
    const focused = [];
    const makeClassList = () => ({
        add: () => {},
        remove: () => {},
        toggle: () => {}
    });
    const chemicalsPanel = {
        style: { display: 'none' }
    };
    const apparatusPanel = {
        style: { display: 'none' }
    };
    const chemicalsTrigger = {
        classList: makeClassList(),
        setAttribute: () => {}
    };
    const apparatusTrigger = {
        classList: makeClassList(),
        setAttribute: () => {}
    };
    const search = { value: 'sodium' };
    const chlorine = {
        style: { display: 'none' },
        dataset: { name: 'Cl2' },
        setAttribute: () => {},
        classList: makeClassList(),
        focus: () => focused.push('chlorine')
    };
    const elements = {
        'sub-panel-chemicals': chemicalsPanel,
        'sub-panel-apparatus': apparatusPanel,
        'trigger-chemicals': chemicalsTrigger,
        'trigger-apparatus': apparatusTrigger,
        'chem-search-input': search,
        'chem-item-Cl2': chlorine
    };
    globalThis.document.getElementById = id => elements[id] || null;
    globalThis.document.querySelector = () => null;
    globalThis.document.querySelectorAll = selector => {
        if (selector === '.chemical-card') return [chlorine];
        if (selector === '.floating-popover-panel') {
            return [chemicalsPanel, apparatusPanel];
        }
        if (selector === '.toolbar-trigger-btn') {
            return [chemicalsTrigger, apparatusTrigger];
        }
        return [];
    };
    updateLabState({ selectedChemicals: ['Na'], currentVessel: 'flask' });

    advanceFirstExperimentGuide();

    assert.equal(search.value, '');
    assert.equal(chlorine.style.display, '');
    assert.equal(chlorine.disabled, false);
    assert.equal(chemicalsPanel.style.display, 'block');
    assert.equal(apparatusPanel.style.display, 'none');
    assert.deepEqual(focused, ['chlorine']);
});
