import * as config from '../configuration/config.js';
import { openCustomPopover } from '../userInterface/ui.js';

export type FirstExperimentStep =
    | 'sodium'
    | 'chlorine'
    | 'beaker'
    | 'analyze'
    | 'complete';

interface StepCopy {
    label: string;
    title: string;
    instruction: string | null;
    progress: number;
}

const STEP_COPY: Record<FirstExperimentStep, StepCopy> = {
    sodium: {
        label: 'Step 1 of 4',
        title: 'Add sodium',
        instruction: 'Open Chemicals and select Sodium (Na). OmniLab will then mark its supported partner.',
        progress: 1
    },
    chlorine: {
        label: 'Step 2 of 4',
        title: 'Add chlorine',
        instruction: null,
        progress: 2
    },
    beaker: {
        label: 'Step 3 of 4',
        title: 'Choose a beaker',
        instruction: null,
        progress: 3
    },
    analyze: {
        label: 'Step 4 of 4',
        title: 'Run the prediction',
        instruction: null,
        progress: 4
    },
    complete: {
        label: 'Experiment complete',
        title: 'Read the result',
        instruction: 'Compare the equation and explanation, then read all three safety rules. This prediction does not replace a physical lab procedure.',
        progress: 4
    }
};

export function getFirstExperimentInstruction(
    step: FirstExperimentStep
): string | null {
    return STEP_COPY[step].instruction;
}

export function getFirstExperimentStep(
    selectedChemicals: string[],
    vessel: string,
    hasCompleteResult: boolean
): FirstExperimentStep {
    if (hasCompleteResult) return 'complete';
    if (!selectedChemicals.includes('Na')) return 'sodium';
    if (!selectedChemicals.includes('Cl2')) return 'chlorine';
    if (vessel !== 'beaker') return 'beaker';
    return 'analyze';
}

function resultIsComplete(): boolean {
    const panel = document.getElementById('ai-response-content');
    return Boolean(
        panel?.querySelector('.reaction-equation')
        && panel.querySelector('.reaction-explanation')
        && panel.querySelectorAll('.safety-list li').length === 3
    );
}

function clearGuideTargets(): void {
    document.querySelectorAll('.first-experiment-target').forEach(element => {
        element.classList.remove('first-experiment-target');
    });
}

function chemicalTarget(chemicalId: string): HTMLElement | null {
    const trigger = document.getElementById('trigger-chemicals');
    const panel = document.getElementById('sub-panel-chemicals');
    const chemical = document.getElementById(`chem-item-${chemicalId}`);
    return panel?.style.display === 'block' && chemical ? chemical : trigger;
}

function apparatusTarget(): HTMLElement | null {
    const trigger = document.getElementById('trigger-apparatus');
    const panel = document.getElementById('sub-panel-apparatus');
    const beaker = document.getElementById('opt-beaker');
    return panel?.style.display === 'block' && beaker ? beaker : trigger;
}

function updateChemicalChoices(step: FirstExperimentStep): void {
    document.querySelectorAll<HTMLButtonElement>('.chemical-card').forEach(card => {
        const isTarget = (
            (step === 'sodium' && card.dataset.name === 'Na')
            || (step === 'chlorine' && card.dataset.name === 'Cl2')
        );
        card.disabled = !isTarget;
        card.setAttribute(
            'aria-disabled',
            card.disabled ? 'true' : 'false'
        );
    });
}

function targetForStep(step: FirstExperimentStep): HTMLElement | null {
    if (step === 'sodium') return chemicalTarget('Na');
    if (step === 'chlorine') return chemicalTarget('Cl2');
    if (step === 'beaker') return apparatusTarget();
    if (step === 'analyze') {
        return document.getElementById('btn-fire-analysis');
    }
    return (
        document.querySelector<HTMLElement>('.safety-matrix-block')
        ?? document.getElementById('ai-response-content')
    );
}

function getCurrentStep(): FirstExperimentStep {
    const state = config.getLabState();
    return getFirstExperimentStep(
        state.selectedChemicals,
        state.currentVessel,
        resultIsComplete()
    );
}

function openPanelForStep(step: FirstExperimentStep): void {
    if (step === 'sodium' || step === 'chlorine') {
        // A search for the previous chemical must not hide the next step.
        const search = document.getElementById('chem-search-input') as HTMLInputElement | null;
        if (search) search.value = '';
        document.querySelectorAll<HTMLElement>('.chemical-card').forEach(card => {
            card.style.display = '';
        });
        openCustomPopover('chemicals', false);
    } else if (step === 'beaker') {
        openCustomPopover('apparatus', false);
    }
}

export function focusFirstExperimentTarget(
    step: FirstExperimentStep
): void {
    if (!window.firstExperiment || step === 'complete') return;
    targetForStep(step)?.focus();
}

export function syncFirstExperimentGuide(): void {
    if (!window.firstExperiment) return;

    const step = getCurrentStep();
    const copy = STEP_COPY[step];
    const label = document.getElementById('first-experiment-step');
    const title = document.getElementById('first-experiment-title');
    const instruction = document.getElementById('first-experiment-instruction');

    if (label) label.textContent = copy.label;
    if (title) title.textContent = copy.title;
    if (instruction) {
        instruction.hidden = copy.instruction === null;
        instruction.textContent = copy.instruction ?? '';
    }

    document.querySelectorAll<HTMLElement>('[data-guide-step]').forEach(marker => {
        const markerStep = Number(marker.dataset.guideStep || 0);
        marker.classList.toggle('is-complete', markerStep < copy.progress || step === 'complete');
        marker.classList.toggle('is-current', markerStep === copy.progress && step !== 'complete');
        if (markerStep === copy.progress && step !== 'complete') {
            marker.setAttribute('aria-current', 'step');
        } else {
            marker.removeAttribute('aria-current');
        }
    });

    clearGuideTargets();
    updateChemicalChoices(step);
    const analyzeButton = document.getElementById(
        'btn-fire-analysis'
    ) as HTMLButtonElement | null;
    if (analyzeButton) {
        analyzeButton.disabled = step !== 'analyze';
    }
    targetForStep(step)?.classList.add('first-experiment-target');
}

export function advanceFirstExperimentGuide(): void {
    if (!window.firstExperiment) return;
    const step = getCurrentStep();
    openPanelForStep(step);
    syncFirstExperimentGuide();
    focusFirstExperimentTarget(step);
}

export function initializeFirstExperiment(): void {
    if (!window.firstExperiment) return;

    const panel = document.getElementById('ai-response-content');
    const mixture = document.getElementById('current-mixture');
    if (panel) {
        new MutationObserver(syncFirstExperimentGuide).observe(panel, {
            childList: true,
            subtree: true
        });
    }
    if (mixture) {
        new MutationObserver(syncFirstExperimentGuide).observe(mixture, {
            childList: true,
            subtree: true
        });
    }
    window.addEventListener(
        'omnilab:analysis-state-changed',
        syncFirstExperimentGuide
    );
    advanceFirstExperimentGuide();
}
