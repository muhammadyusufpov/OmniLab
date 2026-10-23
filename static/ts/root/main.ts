import * as config from '../configuration/config.js';
import * as ui from '../userInterface/ui.js';
import * as render from '../rendering/render.js';
import * as interactions from '../interactions/interactions.js';
import * as firstExperiment from '../firstExperiment/firstExperiment.js';
import { capture } from '../analytics/analytics.js';
import { settleLiquid } from '../rendering/liquidMotion.js';
import { bindApparatusTools, updateApparatus } from '../apparatus/apparatus.js';

declare global {
    interface Window {
        chemicalDataUrl?: string;
        toggleCustomPopover: typeof ui.toggleCustomPopover;
        selectVessel: typeof ui.selectVessel;
        toggleTheme: typeof ui.toggleTheme;
        resetLaboratory: typeof interactions.resetLaboratory;
        fireAIAnalysis: typeof interactions.fireAIAnalysis;
        allowDrop: typeof interactions.allowDrop;
        drop: typeof interactions.drop;
    }
}

document.addEventListener("DOMContentLoaded", function(): void {
    capture('lab_viewed', { route: window.location.pathname });
    const reactionDemo = config.getReactionDemoConfig();
    if (reactionDemo) {
        const visitSource = config.getVisitSource();
        capture('reaction_demo_entered', {
            demo_version: reactionDemo.version,
            chemical_count: reactionDemo.selectedChemicals.length,
            vessel: reactionDemo.vessel,
            ...(visitSource ? { visit_source: visitSource } : {})
        });
    }
    ui.resizeCanvas();
    requestAnimationFrame(engineLoop);
    interactions.setupCanvasDrag();
    ui.setupSearchFunction();
    firstExperiment.initializeFirstExperiment();

    const burnerOpt = document.getElementById('opt-burner');
    if (burnerOpt) {
        burnerOpt.addEventListener('click', () => ui.selectVessel('burner'));
    }
    bindApparatusTools();

    const jsonUrl: string = window.chemicalDataUrl || "/static/js/chemicaldata.json";

    fetch(jsonUrl) 
        .then((response: Response) => {
            if (!response.ok) throw new Error("File Not Found! Status: " + response.status);
            return response.json();
        })
        .then((data: any) => {
            config.updateLabState({ chemicalDatabase: data });
            ui.buildChemicalMenu((name: string, color: string) => {
                interactions.addChemicalToLab(name, color);
                firstExperiment.advanceFirstExperimentGuide();
            });
            firstExperiment.syncFirstExperimentGuide();
        })
        .catch((error: any) => console.error("Error loading json:", error));

    if (config.canvas) {
        config.canvas.addEventListener('dragover', interactions.allowDrop as EventListener);
        config.canvas.addEventListener('drop', interactions.drop as EventListener);
    }

    const chemBtn = document.getElementById('trigger-chemicals');
    const appBtn = document.getElementById('trigger-apparatus');
    const themeBtn = document.getElementById('trigger-theme');
    const resetBtn = document.getElementById('btn-reset-lab');
    const analyzeBtn = document.getElementById('btn-fire-analysis');
    const workspace = document.getElementById('lab-workspace');
    const hideAnalysisBtn = document.getElementById('btn-hide-analysis') as HTMLButtonElement | null;
    const showAnalysisBtn = document.getElementById('btn-show-analysis') as HTMLButtonElement | null;
    const resultTab = document.getElementById('analysis-tab-result') as HTMLButtonElement | null;
    const chatTab = document.getElementById('analysis-tab-chat') as HTMLButtonElement | null;
    const resultView = document.getElementById('analysis-view-result');
    const chatView = document.getElementById('analysis-view-chat');
    const chatForm = document.getElementById('chat-preview-form') as HTMLFormElement | null;
    const chatInput = document.getElementById('chat-preview-input') as HTMLTextAreaElement | null;
    const chatSend = document.getElementById('chat-preview-send') as HTMLButtonElement | null;
    const chatModel = document.getElementById('chat-model-select') as HTMLSelectElement | null;
    const chatVersion = document.getElementById('chat-version-select') as HTMLSelectElement | null;
    const chatOutput = document.getElementById('chat-preview-output');
    const previewVersions: Record<string, string[]> = {
        GPT: ['GPT Standard', 'GPT Fast'],
        Claude: ['Claude Standard', 'Claude Fast'],
        Grok: ['Grok Standard', 'Grok Fast'],
        DeepSeek: ['DeepSeek Standard', 'DeepSeek Fast'],
        Qwen: ['Qwen 3.5 Flash', 'Qwen 3.5']
    };

    function syncChatVersions(): void {
        if (!chatModel || !chatVersion) return;
        chatVersion.replaceChildren(...(previewVersions[chatModel.value] || []).map((version) => new Option(version, version)));
    }

    function syncChatSend(): void {
        if (chatInput && chatSend) chatSend.disabled = !chatInput.value.trim();
    }

    function previewSendQuestion(): void {
        if (!chatInput || !chatOutput) return;
        const question = chatInput.value.trim();
        if (!question) return;
        const message = document.createElement('div');
        message.className = 'chat-preview-question';
        message.textContent = question;
        const response = document.createElement('p');
        response.className = 'chat-preview-response';
        response.textContent = 'Preview only. No question was sent to an AI model.';
        chatOutput.replaceChildren(message, response);
        chatInput.value = '';
        syncChatSend();
        chatInput.focus();
    }

    chatModel?.addEventListener('change', syncChatVersions);
    chatInput?.addEventListener('input', syncChatSend);
    chatInput?.addEventListener('keydown', (event: KeyboardEvent) => {
        if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
        event.preventDefault();
        previewSendQuestion();
    });
    chatForm?.addEventListener('submit', (event: SubmitEvent) => {
        event.preventDefault();
        previewSendQuestion();
    });
    syncChatVersions();
    syncChatSend();

    function showAnalysisView(view: 'result' | 'chat'): void {
        if (!resultTab || !chatTab || !resultView || !chatView) return;
        const showResult = view === 'result';
        resultView.hidden = !showResult;
        chatView.hidden = showResult;
        resultTab.classList.toggle('is-active', showResult);
        chatTab.classList.toggle('is-active', !showResult);
        resultTab.setAttribute('aria-selected', String(showResult));
        chatTab.setAttribute('aria-selected', String(!showResult));
        resultTab.tabIndex = showResult ? 0 : -1;
        chatTab.tabIndex = showResult ? -1 : 0;
    }

    resultTab?.addEventListener('click', () => showAnalysisView('result'));
    chatTab?.addEventListener('click', () => showAnalysisView('chat'));
    for (const tab of [resultTab, chatTab]) {
        tab?.addEventListener('keydown', (event: KeyboardEvent) => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            event.preventDefault();
            const nextView = tab === resultTab ? 'chat' : 'result';
            showAnalysisView(nextView);
            (nextView === 'result' ? resultTab : chatTab)?.focus();
        });
    }

    function setAnalysisCollapsed(collapsed: boolean): void {
        if (!workspace || !hideAnalysisBtn || !showAnalysisBtn) return;
        workspace.classList.toggle('is-analysis-collapsed', collapsed);
        hideAnalysisBtn.setAttribute('aria-expanded', String(!collapsed));
        showAnalysisBtn.setAttribute('aria-expanded', String(!collapsed));
        showAnalysisBtn.hidden = !collapsed;
        requestAnimationFrame(() => {
            ui.resizeCanvas();
            (collapsed ? showAnalysisBtn : hideAnalysisBtn).focus();
        });
    }

    hideAnalysisBtn?.addEventListener('click', () => setAnalysisCollapsed(true));
    showAnalysisBtn?.addEventListener('click', () => setAnalysisCollapsed(false));

    if (chemBtn) chemBtn.addEventListener('click', (e: MouseEvent) => {
        ui.toggleCustomPopover(e, 'chemicals');
        firstExperiment.syncFirstExperimentGuide();
    });
    if (appBtn) appBtn.addEventListener('click', (e: MouseEvent) => {
        ui.toggleCustomPopover(e, 'apparatus');
        firstExperiment.syncFirstExperimentGuide();
    });
    if (themeBtn) themeBtn.addEventListener('click', ui.toggleTheme);
    if (resetBtn) resetBtn.addEventListener('click', () => {
        interactions.resetLaboratory();
        firstExperiment.advanceFirstExperimentGuide();
    });
    if (analyzeBtn) analyzeBtn.addEventListener('click', interactions.fireAIAnalysis);

    const beakerOpt = document.getElementById('opt-beaker');
    const tubeOpt = document.getElementById('opt-tube');
    const flaskOpt = document.getElementById('opt-flask');
    const cylinderOpt = document.getElementById('opt-cylinder');

    if (beakerOpt) beakerOpt.addEventListener('click', () => {
        ui.selectVessel('beaker');
        firstExperiment.advanceFirstExperimentGuide();
    });
    if (tubeOpt) tubeOpt.addEventListener('click', () => {
        ui.selectVessel('tube');
        firstExperiment.syncFirstExperimentGuide();
    });
    if (flaskOpt) flaskOpt.addEventListener('click', () => {
        ui.selectVessel('flask');
        firstExperiment.syncFirstExperimentGuide();
    });
    if (cylinderOpt) cylinderOpt.addEventListener('click', () => {
        ui.selectVessel('cylinder');
        firstExperiment.syncFirstExperimentGuide();
    });

    document.addEventListener('click', ui.closeAllPopovers);
    window.addEventListener('resize', ui.resizeCanvas);
});

let lastFrameTime = 0;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

function engineLoop(now: number): void {
    const state = config.getLabState();
    const elapsed = lastFrameTime ? Math.min(now - lastFrameTime, 50) / 1000 : 1 / 60;
    lastFrameTime = now;

    if (state.filterProgress > 0) {
        updateApparatus(now, elapsed);
    } else if (state.currentLiquidVol < state.targetLiquidVol) {
        const nextVolume = reducedMotion.matches
            ? state.targetLiquidVol
            : Math.min(state.targetLiquidVol, state.currentLiquidVol + 240 * elapsed);
        config.updateLabState({
            currentLiquidVol: nextVolume,
            streamActive: nextVolume < state.targetLiquidVol,
            waveTime: state.waveTime + (reducedMotion.matches ? 0 : 8 * elapsed)
        });
    } else {
        config.updateLabState({
            streamActive: false,
            currentLiquidVol: state.currentLiquidVol > state.targetLiquidVol
                ? Math.max(state.targetLiquidVol, state.currentLiquidVol - 240 * elapsed)
                : state.currentLiquidVol,
            waveTime: state.currentLiquidVol > 0 && !reducedMotion.matches
                ? state.waveTime + 2 * elapsed
                : state.waveTime
        });
    }
    if (state.currentLiquidVol > 0 && !reducedMotion.matches) {
        config.updateLabState(settleLiquid(config.getLabState(), elapsed));
    }
    if (state.filterProgress === 0) updateApparatus(now, elapsed);
    render.drawVesselAndFluid();
    requestAnimationFrame(engineLoop);
}

window.toggleCustomPopover = ui.toggleCustomPopover;
window.selectVessel = ui.selectVessel;
window.toggleTheme = ui.toggleTheme;
window.resetLaboratory = interactions.resetLaboratory;
window.fireAIAnalysis = interactions.fireAIAnalysis;
window.allowDrop = interactions.allowDrop;
window.drop = interactions.drop;
