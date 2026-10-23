import * as config from '../configuration/config.js';
import * as ui from '../userInterface/ui.js';
import * as render from '../rendering/render.js';
import * as interactions from '../interactions/interactions.js';
import * as firstExperiment from '../firstExperiment/firstExperiment.js';
import { capture } from '../analytics/analytics.js';
import { settleLiquid } from '../rendering/liquidMotion.js';
import { bindApparatusTools, updateApparatus } from '../apparatus/apparatus.js';
document.addEventListener("DOMContentLoaded", function () {
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
    const jsonUrl = window.chemicalDataUrl || "/static/js/chemicaldata.json";
    fetch(jsonUrl)
        .then((response) => {
        if (!response.ok)
            throw new Error("File Not Found! Status: " + response.status);
        return response.json();
    })
        .then((data) => {
        config.updateLabState({ chemicalDatabase: data });
        ui.buildChemicalMenu((name, color) => {
            interactions.addChemicalToLab(name, color);
            firstExperiment.advanceFirstExperimentGuide();
        });
        firstExperiment.syncFirstExperimentGuide();
    })
        .catch((error) => console.error("Error loading json:", error));
    if (config.canvas) {
        config.canvas.addEventListener('dragover', interactions.allowDrop);
        config.canvas.addEventListener('drop', interactions.drop);
    }
    const chemBtn = document.getElementById('trigger-chemicals');
    const appBtn = document.getElementById('trigger-apparatus');
    const themeBtn = document.getElementById('trigger-theme');
    const resetBtn = document.getElementById('btn-reset-lab');
    const analyzeBtn = document.getElementById('btn-fire-analysis');
    const workspace = document.getElementById('lab-workspace');
    const analysisResize = document.getElementById('analysis-resize-handle');
    const hideAnalysisBtn = document.getElementById('btn-hide-analysis');
    const showAnalysisBtn = document.getElementById('btn-show-analysis');
    const resultTab = document.getElementById('analysis-tab-result');
    const chatTab = document.getElementById('analysis-tab-chat');
    const resultView = document.getElementById('analysis-view-result');
    const chatView = document.getElementById('analysis-view-chat');
    const chatForm = document.getElementById('chat-preview-form');
    const chatInput = document.getElementById('chat-preview-input');
    const chatSend = document.getElementById('chat-preview-send');
    const chatModel = document.getElementById('chat-model-select');
    const chatVersion = document.getElementById('chat-version-select');
    const modelPicker = document.getElementById('chat-model-picker');
    const versionPicker = document.getElementById('chat-version-picker');
    const chatOutput = document.getElementById('chat-preview-output');
    const previewVersions = {
        GPT: ['GPT Standard', 'GPT Fast'],
        Claude: ['Claude Standard', 'Claude Fast'],
        Grok: ['Grok Standard', 'Grok Fast'],
        DeepSeek: ['DeepSeek Standard', 'DeepSeek Fast'],
        Qwen: ['Qwen 3.5 Flash', 'Qwen 3.5']
    };
    function syncChatVersions() {
        if (!chatModel || !chatVersion)
            return;
        chatVersion.replaceChildren(...(previewVersions[chatModel.value] || []).map((version) => new Option(version, version)));
        renderChatPickers();
    }
    const modelIcons = { GPT: '✳', Claude: '✻', Grok: '✕', DeepSeek: '✦', Qwen: '✥' };
    function closeChatPickers() {
        for (const picker of [modelPicker, versionPicker]) {
            const trigger = picker?.querySelector('.chat-picker-trigger');
            const menu = picker?.querySelector('.chat-picker-menu');
            if (trigger && menu) {
                trigger.setAttribute('aria-expanded', 'false');
                menu.hidden = true;
            }
        }
    }
    function renderChatPicker(picker, select, family) {
        const trigger = picker?.querySelector('.chat-picker-trigger');
        const menu = picker?.querySelector('.chat-picker-menu');
        if (!trigger || !menu || !select)
            return;
        trigger.replaceChildren();
        const glyph = document.createElement('span');
        glyph.className = 'chat-picker-icon';
        glyph.setAttribute('aria-hidden', 'true');
        if (family)
            glyph.textContent = modelIcons[select.value] || '✦';
        else
            glyph.innerHTML = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M7 13c0-1.7-2-2.3-2-5a5 5 0 0 1 10 0c0 2.7-2 3.3-2 5M7 13h6m-5 2h4m-3 2h2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        const name = document.createElement('span');
        name.className = 'chat-picker-name';
        name.textContent = select.value;
        const chevron = document.createElement('span');
        chevron.className = 'chat-picker-chevron';
        chevron.setAttribute('aria-hidden', 'true');
        chevron.innerHTML = '<span>⌃</span><span>⌄</span>';
        trigger.append(glyph, name);
        if (!family)
            trigger.append(chevron);
        menu.replaceChildren(...Array.from(select.options).map((option) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'chat-picker-option';
            item.setAttribute('role', 'option');
            item.setAttribute('aria-selected', String(option.value === select.value));
            const itemIcon = document.createElement('span');
            itemIcon.className = 'chat-picker-icon';
            itemIcon.setAttribute('aria-hidden', 'true');
            itemIcon.textContent = modelIcons[option.value] || '✦';
            const label = document.createElement('span');
            label.textContent = option.textContent;
            if (family)
                item.append(itemIcon);
            item.append(label);
            if (option.value === select.value) {
                const check = document.createElement('span');
                check.className = 'chat-picker-check';
                check.setAttribute('aria-hidden', 'true');
                check.textContent = '✓';
                item.append(check);
            }
            item.addEventListener('click', () => {
                select.value = option.value;
                select.dispatchEvent(new Event('change', { bubbles: true }));
                renderChatPicker(picker, select, family);
                closeChatPickers();
                trigger.focus();
            });
            return item;
        }));
    }
    function renderChatPickers() {
        renderChatPicker(modelPicker, chatModel, true);
        renderChatPicker(versionPicker, chatVersion, false);
    }
    for (const picker of [modelPicker, versionPicker]) {
        const trigger = picker?.querySelector('.chat-picker-trigger');
        const menu = picker?.querySelector('.chat-picker-menu');
        trigger?.addEventListener('click', () => {
            const open = !!menu?.hidden;
            closeChatPickers();
            if (menu && open) {
                menu.hidden = false;
                trigger.setAttribute('aria-expanded', 'true');
            }
        });
        trigger?.addEventListener('keydown', (event) => {
            if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp')
                return;
            event.preventDefault();
            trigger.click();
            menu?.querySelector('.chat-picker-option')?.focus();
        });
        menu?.addEventListener('keydown', (event) => {
            const items = Array.from(menu.querySelectorAll('.chat-picker-option'));
            const index = items.indexOf(document.activeElement);
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
            }
            if (event.key === 'Escape') {
                closeChatPickers();
                trigger?.focus();
            }
        });
    }
    document.addEventListener('pointerdown', (event) => {
        if (!modelPicker?.contains(event.target) && !versionPicker?.contains(event.target))
            closeChatPickers();
    });
    function syncChatSend() {
        if (chatInput && chatSend)
            chatSend.disabled = !chatInput.value.trim();
    }
    function previewSendQuestion() {
        if (!chatInput || !chatOutput)
            return;
        const question = chatInput.value.trim();
        if (!question)
            return;
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
    chatInput?.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' || event.shiftKey || event.isComposing)
            return;
        event.preventDefault();
        previewSendQuestion();
    });
    chatForm?.addEventListener('submit', (event) => {
        event.preventDefault();
        previewSendQuestion();
    });
    syncChatVersions();
    syncChatSend();
    function showAnalysisView(view) {
        if (!resultTab || !chatTab || !resultView || !chatView)
            return;
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
        tab?.addEventListener('keydown', (event) => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight')
                return;
            event.preventDefault();
            const nextView = tab === resultTab ? 'chat' : 'result';
            showAnalysisView(nextView);
            (nextView === 'result' ? resultTab : chatTab)?.focus();
        });
    }
    function setAnalysisCollapsed(collapsed) {
        if (!workspace || !hideAnalysisBtn || !showAnalysisBtn)
            return;
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
    if (workspace && analysisResize) {
        const sidebar = document.getElementById('reaction-analysis');
        const widthBounds = () => {
            const total = workspace.getBoundingClientRect().width;
            return [320, Math.max(320, Math.min(620, total * .5, total - 420))];
        };
        const setWidth = (requested) => {
            const [min, max] = widthBounds();
            const width = Math.round(Math.max(min, Math.min(max, requested)));
            workspace.style.setProperty('--analysis-width', `${width}px`);
            analysisResize.setAttribute('aria-valuenow', String(width));
            analysisResize.setAttribute('aria-valuemax', String(Math.round(max)));
            requestAnimationFrame(ui.resizeCanvas);
        };
        analysisResize.addEventListener('pointerdown', (event) => {
            if (window.matchMedia('(max-width: 991.98px)').matches || !sidebar)
                return;
            event.preventDefault();
            const startX = event.clientX;
            const startWidth = sidebar.getBoundingClientRect().width;
            analysisResize.setPointerCapture(event.pointerId);
            const move = (motion) => setWidth(startWidth + startX - motion.clientX);
            const end = () => {
                analysisResize.removeEventListener('pointermove', move);
                analysisResize.removeEventListener('pointerup', end);
                analysisResize.removeEventListener('pointercancel', end);
            };
            analysisResize.addEventListener('pointermove', move);
            analysisResize.addEventListener('pointerup', end);
            analysisResize.addEventListener('pointercancel', end);
        });
        analysisResize.addEventListener('keydown', (event) => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight')
                return;
            event.preventDefault();
            setWidth((sidebar?.getBoundingClientRect().width || 320) + (event.key === 'ArrowLeft' ? 20 : -20));
        });
        window.addEventListener('resize', () => {
            if (workspace.style.getPropertyValue('--analysis-width') && sidebar)
                setWidth(sidebar.getBoundingClientRect().width);
        });
    }
    if (chemBtn)
        chemBtn.addEventListener('click', (e) => {
            ui.toggleCustomPopover(e, 'chemicals');
            firstExperiment.syncFirstExperimentGuide();
        });
    if (appBtn)
        appBtn.addEventListener('click', (e) => {
            ui.toggleCustomPopover(e, 'apparatus');
            firstExperiment.syncFirstExperimentGuide();
        });
    if (themeBtn)
        themeBtn.addEventListener('click', ui.toggleTheme);
    if (resetBtn)
        resetBtn.addEventListener('click', () => {
            interactions.resetLaboratory();
            firstExperiment.advanceFirstExperimentGuide();
        });
    if (analyzeBtn)
        analyzeBtn.addEventListener('click', interactions.fireAIAnalysis);
    const beakerOpt = document.getElementById('opt-beaker');
    const tubeOpt = document.getElementById('opt-tube');
    const flaskOpt = document.getElementById('opt-flask');
    const cylinderOpt = document.getElementById('opt-cylinder');
    if (beakerOpt)
        beakerOpt.addEventListener('click', () => {
            ui.selectVessel('beaker');
            firstExperiment.advanceFirstExperimentGuide();
        });
    if (tubeOpt)
        tubeOpt.addEventListener('click', () => {
            ui.selectVessel('tube');
            firstExperiment.syncFirstExperimentGuide();
        });
    if (flaskOpt)
        flaskOpt.addEventListener('click', () => {
            ui.selectVessel('flask');
            firstExperiment.syncFirstExperimentGuide();
        });
    if (cylinderOpt)
        cylinderOpt.addEventListener('click', () => {
            ui.selectVessel('cylinder');
            firstExperiment.syncFirstExperimentGuide();
        });
    document.addEventListener('click', ui.closeAllPopovers);
    window.addEventListener('resize', ui.resizeCanvas);
});
let lastFrameTime = 0;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
function engineLoop(now) {
    const state = config.getLabState();
    const elapsed = lastFrameTime ? Math.min(now - lastFrameTime, 50) / 1000 : 1 / 60;
    lastFrameTime = now;
    if (state.filterProgress > 0) {
        updateApparatus(now, elapsed);
    }
    else if (state.currentLiquidVol < state.targetLiquidVol) {
        const nextVolume = reducedMotion.matches
            ? state.targetLiquidVol
            : Math.min(state.targetLiquidVol, state.currentLiquidVol + 240 * elapsed);
        config.updateLabState({
            currentLiquidVol: nextVolume,
            streamActive: nextVolume < state.targetLiquidVol,
            waveTime: state.waveTime + (reducedMotion.matches ? 0 : 8 * elapsed)
        });
    }
    else {
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
    if (state.filterProgress === 0)
        updateApparatus(now, elapsed);
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
//# sourceMappingURL=main.js.map