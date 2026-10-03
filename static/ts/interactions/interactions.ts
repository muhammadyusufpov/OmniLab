import * as config from '../configuration/config.js';
import {
    closeAllPopovers,
    refreshChemicalMenuGuidance
} from '../userInterface/ui.js';
import {
    cancelReactionEffects,
    drawVesselAndFluid,
    triggerThermalBlast
} from '../rendering/render.js';
import { capture, captureLabSetupStarted } from '../analytics/analytics.js';
import {
    bindFeedbackOpenCapture,
    buildFeedbackContactUrl,
    captureFeedbackPromptViewed
} from './feedback.js';
import {
    normalizeReactionEffect,
    normalizePrecipitateColor,
    parseSavedReactionResult,
    type ReactionResult
} from './reactionResult.js';
import {
    readStorageValue,
    removeStorageValue,
    writeStorageValue
} from '../storage/storage.js';

const DEFAULT_REACTION_INSTRUCTION = `
    <div class="text-center mt-5 lab-empty-state">
        <p class="lab-instruction mb-2">Choose a supported pair from Chemicals. Try <strong>Hydrogen and Oxygen</strong> or <strong>Hydrochloric acid and Sodium hydroxide</strong>.</p>
        <a class="lab-demo-link" href="/demo/sodium-chlorine/">
            Open the prepared Sodium and Chlorine demo
            <span class="lab-control-arrow" aria-hidden="true">&rarr;</span>
        </a>
    </div>
`;
const DEMO_REACTION_INSTRUCTION = '<p class="text-center mt-5 lab-instruction">This setup is ready. Select Analyze Chemical Reaction to request the prediction.</p>';
const FIRST_EXPERIMENT_INSTRUCTION = `
    <div class="text-center mt-5 lab-empty-state">
        <p class="lab-instruction mb-2">Follow the highlighted control through four short steps. Your equation, explanation, and safety rules will appear here.</p>
    </div>
`;
const REACTION_RETRY_MESSAGE = "OmniLab couldn't complete this prediction. Please try again.";
let activeAnalysisController: AbortController | null = null;
let currentAnalysisRunId = 0;

function getDefaultReactionInstruction(): string {
    return window.firstExperiment
        ? FIRST_EXPERIMENT_INSTRUCTION
        : DEFAULT_REACTION_INSTRUCTION;
}

function getAnalysisAvailabilityMessage(selectedChemicals: string[]): string {
    if (config.isSupportedReactionSetup(selectedChemicals)) {
        return 'Ready to analyze this supported reaction pair.';
    }
    if (selectedChemicals.length === 1) {
        return 'Choose a compatible partner marked in Chemicals.';
    }
    if (selectedChemicals.length > 1) {
        return 'This setup is not supported in OmniLab. Reset and choose a marked compatible pair.';
    }
    return 'Add two chemicals from a supported reaction pair.';
}

function updateAnalysisAvailability(): void {
    const selectedChemicals = config.getLabState().selectedChemicals;
    const setupIsSupported = config.isSupportedReactionSetup(selectedChemicals);
    const analyzeBtn = document.getElementById('btn-fire-analysis') as HTMLButtonElement | null;
    const availabilityMessage = document.getElementById('analysis-availability-message');

    if (analyzeBtn) {
        analyzeBtn.disabled = activeAnalysisController !== null || !setupIsSupported;
    }
    if (availabilityMessage) {
        availabilityMessage.textContent = getAnalysisAvailabilityMessage(selectedChemicals);
    }
}

function setAnalysisPending(pending: boolean): void {
    const analyzeBtn = document.getElementById('btn-fire-analysis') as HTMLButtonElement | null;
    if (!analyzeBtn) return;

    analyzeBtn.setAttribute('aria-busy', pending ? 'true' : 'false');
    updateAnalysisAvailability();
    window.dispatchEvent(new Event('omnilab:analysis-state-changed'));
}

interface IncomingReactionResult extends Omit<ReactionResult, 'effect' | 'precipitate_color'> {
    effect?: unknown;
    precipitate_color?: unknown;
}

interface ReactionData {
    status: 'success' | 'error' | 'insufficient_input' | 'rate_limited';
    message?: string;
    data?: IncomingReactionResult;
}

function normalizeReactionResult(reaction: IncomingReactionResult): ReactionResult {
    const effect = normalizeReactionEffect(
        reaction.effect,
        reaction.precipitate_color
    );
    const precipitateColor = normalizePrecipitateColor(
        effect,
        reaction.precipitate_color
    );
    return {
        equation: reaction.equation,
        explanation: reaction.explanation,
        safety: reaction.safety,
        effect,
        ...(precipitateColor
            ? { precipitate_color: precipitateColor }
            : {})
    };
}

function isSupportedLiquidColor(color: string | null): color is string {
    return color !== null && /^#[0-9a-f]{6}$/i.test(color);
}

export function renderReactionResult(
    panel: HTMLElement,
    reaction: ReactionResult,
    selectedChemicals: string[]
): void {
    const matchingReactionGuides = config.getMatchingReactionGuides(
        selectedChemicals
    );
    const reactionStudyMarkup = matchingReactionGuides.length > 0
        ? `
            <nav class="reaction-study" aria-labelledby="reaction-study-title">
                <p class="reaction-study-label">Study this result</p>
                <h3 class="reaction-study-title" id="reaction-study-title">Follow the chemistry behind the prediction</h3>
                <div class="reaction-study-links">
                    ${matchingReactionGuides.map(guide => `
                    <a href="${guide.href}">
                        <span>${guide.title}</span>
                        <span aria-hidden="true">→</span>
                    </a>
                    `).join('')}
                </div>
            </nav>
        `
        : '';

    panel.innerHTML = `
        <div class="lh-base spectrum-analysis-log animate__animated animate__fadeIn text-body-emphasis" style="font-family: 'UbuntuLocal', sans-serif; font-size: 16px; line-height: 1.6; letter-spacing: 0.3px;">

            <div class="mb-4 core-equation-block p-3 bg-dark text-white rounded-4 shadow-lg border border-secondary border-opacity-25">
                <h3 class="h6 text-white-50 text-uppercase small fw-bold mb-2" style="letter-spacing: 1.5px;">
                    <span class="result-heading-mark me-2 text-info" aria-hidden="true">=</span>Chemical Equation Formula
                </h3>
                <div class="fs-5 text-center py-2 px-2 text-white border border-secondary border-opacity-50 rounded-3 reaction-equation"
                    style="font-family: 'Fira Code', monospace; font-weight: 500; background-color: #1e1e24; letter-spacing: 1.5px;"></div>
                <p class="reaction-result-boundary">Educational prediction, not a verified simulation. It can be incomplete or wrong and cannot replace instructor supervision.</p>
            </div>

            <div class="mb-4 conceptual-breakdown px-2">
                <h3 class="h6 text-body-secondary text-uppercase small fw-bold mb-2">
                    <span class="result-heading-mark me-2 text-info" aria-hidden="true">&equiv;</span>Analysis
                </h3>
                <div class="text-body-emphasis reaction-explanation" style="text-align: justify; text-justify: inter-word;"></div>
            </div>

            <div class="alert alert-warning bg-warning-subtle border-warning border-start border-5 shadow-sm p-3 safety-matrix-block rounded-end">
                <h3 class="h6 text-uppercase small fw-bold mb-2 safety-heading">
                    <span class="result-heading-mark me-2 text-warning" aria-hidden="true">!</span>Safety rules
                </h3>
                <ul class="list-unstyled mb-0 small fw-medium safety-list"></ul>
            </div>

            ${reactionStudyMarkup}

            <aside class="reaction-feedback" aria-labelledby="reaction-feedback-title">
                <p class="reaction-feedback-label">Optional feedback</p>
                <h3 class="reaction-feedback-title" id="reaction-feedback-title">Help us understand your goal</h3>
                <a class="reaction-feedback-link" href="#" aria-label="Answer two quick questions in OmniLab">
                    Answer two quick questions
                    <span class="lab-control-arrow" aria-hidden="true">&nearr;</span>
                </a>
                <p class="reaction-feedback-note">Stays in OmniLab. No lab details are added.</p>
            </aside>

        </div>
    `;

    const equation = panel.querySelector<HTMLElement>('.reaction-equation');
    const explanation = panel.querySelector<HTMLElement>('.reaction-explanation');
    const safetyList = panel.querySelector<HTMLUListElement>('.safety-list');
    const feedbackLink = panel.querySelector<HTMLAnchorElement>('.reaction-feedback-link');
    if (!equation || !explanation || !safetyList || !feedbackLink) return;

    equation.textContent = reaction.equation;
    explanation.textContent = reaction.explanation;
    feedbackLink.href = buildFeedbackContactUrl();
    bindFeedbackOpenCapture(feedbackLink);
    captureFeedbackPromptViewed(feedbackLink);

    const safetyPoints = reaction.safety
        .split('|')
        .map(point => point.trim())
        .filter(point => point.length > 0);

    for (const point of safetyPoints.length > 0 ? safetyPoints : [reaction.safety]) {
        const item = document.createElement('li');
        item.className = 'mb-2';

        const icon = document.createElement('span');
        icon.className = 'safety-rule-mark me-2';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = '!';

        item.append(icon, document.createTextNode(point));
        safetyList.append(item);
    }
}

function renderStatusMessage(
    panel: HTMLElement,
    title: string,
    message: string,
    kind: 'info' | 'danger'
): void {
    panel.innerHTML = kind === 'info'
        ? `
            <div class="alert alert-info bg-info-subtle text-info-emphasis border-info border-start border-5 shadow-sm p-3 rounded-end" role="status">
                <h3 class="h6 fw-bold mb-2"></h3>
                <p class="mb-0"></p>
            </div>
        `
        : '<div class="alert alert-danger bg-danger-subtle text-danger-emphasis border-danger" role="alert"></div>';

    if (kind === 'info') {
        const heading = panel.querySelector<HTMLElement>('h3');
        const body = panel.querySelector<HTMLElement>('p');
        if (heading) heading.textContent = title;
        if (body) body.textContent = message;
        return;
    }

    const body = panel.querySelector<HTMLElement>('[role="alert"]');
    if (body) body.textContent = `${title}: ${message}`;
}

function renderReactionRetry(panel: HTMLElement): void {
    renderStatusMessage(
        panel,
        'Reaction unavailable',
        REACTION_RETRY_MESSAGE,
        'danger'
    );
}

export function setupCanvasDrag(): void {
    if (!config.canvas) return;

    config.canvas.addEventListener('mousedown', function(e: MouseEvent) {
        if (!config.canvas) return;
        const rect = config.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const state = config.getLabState();
        let cx = config.canvas.width / 2 + state.vesselOffsetX;
        let cy = config.canvas.height / 2 + 50 + state.vesselOffsetY;

        let checkCy = state.burnerActive ? cy - 40 : cy;
        let btnX = cx;
        let btnY = checkCy + 110 + 48;

        let dist = Math.sqrt((mouseX - btnX) ** 2 + (mouseY - btnY) ** 2);
        if (dist <= 12) {
            config.updateLabState({ burnerActive: !state.burnerActive });
            drawVesselAndFluid();
            return;
        }

        const currentCy = state.burnerActive ? cy - 40 : cy;
        let clickRadius = state.currentVessel === 'flask' ? 110 : (state.currentVessel === 'beaker' ? 90 : 40);

        if (Math.abs(mouseX - cx) < clickRadius && mouseY > currentCy - 100 && mouseY < currentCy + 110) {
            config.updateLabState({
                isDragging: true,
                dragStartX: e.clientX,
                dragStartY: e.clientY
            });
        }
    });

    window.addEventListener('mousemove', function(e: MouseEvent) {
        const state = config.getLabState();
        if (!state.isDragging) return;

        const dx = e.clientX - state.dragStartX;
        const dy = e.clientY - state.dragStartY;

        config.updateLabState({
            vesselOffsetX: state.vesselOffsetX + dx,
            vesselOffsetY: state.vesselOffsetY + dy,
            dragStartX: e.clientX,
            dragStartY: e.clientY
        });
    });

    window.addEventListener('mouseup', function() {
        config.updateLabState({ isDragging: false });
    });
}

export function allowDrop(ev: DragEvent): void {
    ev.preventDefault();
}

export function addChemicalToLab(
    name: string,
    color: string,
    streamX: number = config.canvas ? config.canvas.width / 2 : 0
): void {
    const state = config.getLabState();

    if (!state.selectedChemicals.includes(name)) {
        const updatedChemicals = [...state.selectedChemicals, name];
        const targetVol = Math.min(updatedChemicals.length * 30, 210);

        config.updateLabState({
            selectedChemicals: updatedChemicals,
            liquidColor: color,
            streamColor: color,
            streamActive: true,
            streamX,
            targetLiquidVol: targetVol
        });

        if (updatedChemicals.length === 1) {
            captureLabSetupStarted({
                vessel: state.currentVessel,
                burner_active: state.burnerActive,
                ...config.getLabEntryAttribution()
            });
        }

        writeStorageValue(
            config.getLabStorageKey('savedChemicals'),
            JSON.stringify(updatedChemicals)
        );
        writeStorageValue(config.getLabStorageKey('savedLiquidColor'), color);

        const mixtureEl = document.getElementById('current-mixture');
        if (mixtureEl) {
            mixtureEl.innerText = updatedChemicals.join(' + ');
        }

        const chemicalCard = document.querySelector<HTMLElement>(
            `.chemical-card[data-name="${name}"]`
        );
        chemicalCard?.setAttribute('aria-pressed', 'true');
    }
    refreshChemicalMenuGuidance();
    updateAnalysisAvailability();
    closeAllPopovers();
}

export function drop(ev: DragEvent): void {
    ev.preventDefault();
    if (!config.canvas || !ev.dataTransfer) return;

    const id = ev.dataTransfer.getData("text");
    const element = document.getElementById(id);
    if (!element) return;

    const name = element.getAttribute('data-name');
    const color = element.getAttribute('data-color');
    if (!name || !color) return;

    const rect = config.canvas.getBoundingClientRect();
    addChemicalToLab(name, color, ev.clientX - rect.left);
}

export function resetLaboratory(): void {
    removeStorageValue(config.getLabStorageKey('savedChemicals'));
    removeStorageValue(config.getLabStorageKey('savedLiquidColor'));
    removeStorageValue(config.getLabStorageKey('savedReaction'));

    currentAnalysisRunId += 1;
    activeAnalysisController?.abort();
    activeAnalysisController = null;
    cancelReactionEffects();

    config.updateLabState({
        selectedChemicals: [],
        targetLiquidVol: 0,
        currentLiquidVol: 0,
        liquidColor: '#3399ff',
        streamColor: '#ffffff',
        splashParticles: [],
        ambientBubbles: [],
        smokeParticles: [],
        explosionParticles: [],
        isBubbling: false,
        precipitateColor: null,
        streamActive: false,
        vesselOffsetX: 0,
        vesselOffsetY: 0
    });
    document.querySelectorAll('.chemical-card').forEach(card => {
        card.setAttribute('aria-pressed', 'false');
    });
    refreshChemicalMenuGuidance();
    setAnalysisPending(false);

    const mixtureEl = document.getElementById('current-mixture');
    if (mixtureEl) {
        mixtureEl.innerText = "Empty Vessel";
    }

    const panel = document.getElementById('ai-response-content');
    if (panel) {
        panel.innerHTML = getDefaultReactionInstruction();
    }
    drawVesselAndFluid();
}

function getCsrfToken(): string {
    const cookiePrefix = 'csrftoken=';
    const csrfCookie = document.cookie
        .split(';')
        .map(cookie => cookie.trim())
        .find(cookie => cookie.startsWith(cookiePrefix));

    return csrfCookie
        ? decodeURIComponent(csrfCookie.slice(cookiePrefix.length))
        : '';
}

export function fireAIAnalysis(): void {
    if (activeAnalysisController) return;

    const state = config.getLabState();
    if (!config.isSupportedReactionSetup(state.selectedChemicals)) {
        updateAnalysisAvailability();
        return;
    }

    const panel = document.getElementById('ai-response-content');
    if (!panel) return;

    const requestController = new AbortController();
    activeAnalysisController = requestController;
    setAnalysisPending(true);
    const analysisRunId = ++currentAnalysisRunId;
    const analysisStartedAt = performance.now();
    capture('reaction_analysis_started', {
        chemical_count: state.selectedChemicals.length,
        vessel: state.currentVessel,
        burner_active: state.burnerActive
    });

    panel.innerHTML = '<div class="text-center mt-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-2 fw-bold text-body-secondary">Analyzing chemical reaction...</p></div>';

    let formData = new FormData();
    formData.append('query', state.selectedChemicals.join(' + '));

    fetch('/ai_insights/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCsrfToken()
        },
        body: formData,
        credentials: 'same-origin',
        signal: requestController.signal
    })
    .then(res => res.text())
    .then(rawText => {
        if (analysisRunId !== currentAnalysisRunId) return;
        const cleanedText = rawText.replace(/[\n\r\t]/g, ' ');
        const resData: ReactionData = JSON.parse(cleanedText);

        if (resData.status === 'rate_limited') {
            capture('reaction_analysis_failed', {
                stage: 'rate_limited',
                duration_ms: Math.round(performance.now() - analysisStartedAt)
            });
            renderStatusMessage(
                panel,
                'Please wait before trying again',
                resData.message || 'This network has reached its reaction analysis limit.',
                'info'
            );
        } else if (resData.status === 'insufficient_input') {
            capture('reaction_analysis_failed', {
                stage: 'insufficient_input',
                duration_ms: Math.round(performance.now() - analysisStartedAt)
            });
            removeStorageValue(config.getLabStorageKey('savedReaction'));
            renderStatusMessage(
                panel,
                'Try a different setup',
                resData.message || 'Add another selected chemical and try again.',
                'info'
            );
        } else if (resData.status === 'success' && resData.data) {
            const reaction = normalizeReactionResult(resData.data);
            capture('reaction_analysis_completed', {
                chemical_count: state.selectedChemicals.length,
                vessel: state.currentVessel,
                effect: reaction.effect,
                duration_ms: Math.round(performance.now() - analysisStartedAt),
                ...config.getLabEntryAttribution()
            });
            writeStorageValue(
                config.getLabStorageKey('savedReaction'),
                JSON.stringify(reaction)
            );
            renderReactionResult(panel, reaction, state.selectedChemicals);

            config.updateLabState({
                isBubbling: false,
                precipitateColor: reaction.effect === 'precipitate'
                    ? reaction.precipitate_color || null
                    : null
            });

            if (reaction.effect === 'explosion') {
                triggerThermalBlast();
            }
            else if (reaction.effect === 'bubble') {
                const currentState = config.getLabState();
                config.updateLabState({
                    isBubbling: true,
                    targetLiquidVol: Math.min(currentState.targetLiquidVol + 40, 210)
                });
            }

        } else {
            capture('reaction_analysis_failed', {
                stage: 'response',
                duration_ms: Math.round(performance.now() - analysisStartedAt)
            });
            renderReactionRetry(panel);
        }
    })
    .catch(() => {
        if (requestController.signal.aborted || analysisRunId !== currentAnalysisRunId) return;
        capture('reaction_analysis_failed', {
            stage: 'network_or_parse',
            duration_ms: Math.round(performance.now() - analysisStartedAt)
        });
        renderReactionRetry(panel);
    })
    .finally(() => {
        if (analysisRunId !== currentAnalysisRunId) return;
        activeAnalysisController = null;
        setAnalysisPending(false);
    });
}

document.addEventListener("DOMContentLoaded", () => {
    const reactionDemo = config.getReactionDemoConfig();
    const chemicalsStorageKey = config.getLabStorageKey('savedChemicals');
    const liquidColorStorageKey = config.getLabStorageKey('savedLiquidColor');
    const reactionStorageKey = config.getLabStorageKey('savedReaction');
    const storedChemicals = readStorageValue(chemicalsStorageKey);
    const savedChemicals = config.parseSavedChemicals(storedChemicals);
    const storedLiquidColor = readStorageValue(liquidColorStorageKey);
    const savedLiquidColor = isSupportedLiquidColor(storedLiquidColor)
        ? storedLiquidColor
        : null;
    if (storedLiquidColor && !savedLiquidColor) {
        removeStorageValue(liquidColorStorageKey);
    }
    if (storedChemicals !== null && savedChemicals === null) {
        removeStorageValue(chemicalsStorageKey);
    }
    const preparedChemicals = savedChemicals
        ?? reactionDemo?.selectedChemicals
        ?? [];

    if (savedChemicals === null && reactionDemo) {
        writeStorageValue(
            chemicalsStorageKey,
            JSON.stringify(reactionDemo.selectedChemicals)
        );
        writeStorageValue(liquidColorStorageKey, reactionDemo.liquidColor);
    }

    if (preparedChemicals.length > 0) {
        config.updateLabState({
            selectedChemicals: preparedChemicals,
            currentVessel: reactionDemo?.vessel || config.getLabState().currentVessel
        });

        const mixtureEl = document.getElementById('current-mixture');
        if (mixtureEl) {
            mixtureEl.innerText = preparedChemicals.join(' + ');
        }

        const vol = Math.min(preparedChemicals.length * 30, 210);
        config.updateLabState({
            targetLiquidVol: vol,
            currentLiquidVol: vol
        });
    } else {
        const mixtureEl = document.getElementById('current-mixture');
        if (mixtureEl) {
            mixtureEl.innerText = "Empty Vessel";
        }
    }
    updateAnalysisAvailability();

    const preparedLiquidColor = savedLiquidColor || reactionDemo?.liquidColor;
    if (preparedLiquidColor) {
        config.updateLabState({ liquidColor: preparedLiquidColor });
    }

    if (preparedChemicals.length > 0 || preparedLiquidColor) {
        drawVesselAndFluid();
    }

    const panel = document.getElementById('ai-response-content');
    if (!panel) return;

    const savedData = readStorageValue(reactionStorageKey);
    const savedReaction = parseSavedReactionResult(savedData);
    if (savedReaction) {
        writeStorageValue(reactionStorageKey, JSON.stringify(savedReaction));
        renderReactionResult(panel, savedReaction, preparedChemicals);
        if (savedReaction.effect === 'precipitate') {
            config.updateLabState({
                precipitateColor: savedReaction.precipitate_color || null
            });
            drawVesselAndFluid();
        }
    } else {
        if (savedData !== null) {
            removeStorageValue(reactionStorageKey);
        }
        panel.innerHTML = reactionDemo && preparedChemicals.length > 0
            ? DEMO_REACTION_INSTRUCTION
            : getDefaultReactionInstruction();
    }
});
