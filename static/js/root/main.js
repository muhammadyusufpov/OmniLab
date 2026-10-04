import * as config from '../configuration/config.js';
import * as ui from '../userInterface/ui.js';
import * as render from '../rendering/render.js';
import * as interactions from '../interactions/interactions.js';
import * as firstExperiment from '../firstExperiment/firstExperiment.js';
import { capture } from '../analytics/analytics.js';
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
    document.addEventListener('click', ui.closeAllPopovers);
    window.addEventListener('resize', ui.resizeCanvas);
});
let lastFrameTime = 0;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
function engineLoop(now) {
    const state = config.getLabState();
    const elapsed = lastFrameTime ? Math.min(now - lastFrameTime, 50) / 1000 : 1 / 60;
    lastFrameTime = now;
    if (state.currentLiquidVol < state.targetLiquidVol) {
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