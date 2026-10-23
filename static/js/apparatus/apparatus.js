import * as config from '../configuration/config.js';
import { pourIntoLiquid } from '../rendering/liquidMotion.js';
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
function announce(message) {
    const status = document.getElementById('apparatus-status');
    if (status)
        status.textContent = message;
}
function syncPipetteButton(loaded) {
    const button = document.getElementById('tool-pipette');
    if (!button)
        return;
    button.textContent = loaded ? 'Return pipette sample' : 'Pipette sample';
    button.setAttribute('aria-pressed', String(loaded));
}
function usePipette() {
    const state = config.getLabState();
    if (state.filterProgress > 0) {
        announce('Reset the setup before taking another sample.');
        return;
    }
    if (state.pipetteAmount > 0) {
        config.updateLabState({
            pipetteAmount: 0,
            targetLiquidVol: state.targetLiquidVol + state.pipetteAmount,
            ...(!reducedMotion.matches ? pourIntoLiquid(state) : {})
        });
        syncPipetteButton(false);
        announce('The pipette returned its sample to the vessel. This is a visual technique, not a measured dose.');
    }
    else if (state.currentLiquidVol >= 12 && state.targetLiquidVol >= 12) {
        config.updateLabState({
            pipetteAmount: 12,
            targetLiquidVol: state.targetLiquidVol - 12
        });
        syncPipetteButton(true);
        announce('The pipette holds a small sample. Select it again to return the liquid. The volume is not calibrated.');
    }
    else {
        announce('Add a chemical before using the pipette.');
    }
}
function stir() {
    const state = config.getLabState();
    if (state.currentLiquidVol <= 0 || state.filterProgress > 0) {
        announce('Add liquid to a vessel before stirring.');
        return;
    }
    config.updateLabState({ stirringUntil: reducedMotion.matches ? 0 : performance.now() + 2600 });
    announce('The glass rod stirs the liquid. Stirring does not change the predicted reaction.');
}
function filter() {
    const state = config.getLabState();
    if (!state.precipitateColor || state.currentLiquidVol <= 0 || state.filterProgress > 0 || state.currentLiquidVol < state.targetLiquidVol) {
        announce('Analyze a supported reaction that forms a precipitate before filtering.');
        return;
    }
    if (state.pipetteAmount > 0) {
        announce('Return the pipette sample before filtering.');
        return;
    }
    config.updateLabState({
        filterProgress: 0.001,
        stirringUntil: 0
    });
    announce('Liquid passes through filter paper. The predicted solid stays on the paper. Reset to try another setup.');
}
export function bindApparatusTools() {
    const actions = {
        'tool-pipette': usePipette,
        'tool-stir': stir,
        'tool-filter': filter
    };
    for (const [id, action] of Object.entries(actions)) {
        document.getElementById(id)?.addEventListener('click', event => {
            event.stopPropagation();
            action();
        });
    }
    document.getElementById('btn-reset-lab')?.addEventListener('click', () => {
        syncPipetteButton(false);
        announce('Tools show a visual technique. Volumes are not calibrated. Results are educational estimates.');
    });
}
export function updateApparatus(now, elapsed) {
    const state = config.getLabState();
    if (state.stirringUntil > now && !reducedMotion.matches) {
        config.updateLabState({
            liquidRippleVelocity: Math.min(90, state.liquidRippleVelocity + 65 * elapsed),
            waveTime: state.waveTime + 15 * elapsed
        });
    }
    if (state.filterProgress > 0 && state.filterProgress < 1) {
        const transfer = reducedMotion.matches
            ? state.currentLiquidVol
            : Math.min(state.currentLiquidVol, 42 * elapsed);
        const remaining = Math.max(0, state.currentLiquidVol - transfer);
        config.updateLabState({
            currentLiquidVol: remaining,
            targetLiquidVol: remaining,
            filteredLiquidVol: state.filteredLiquidVol + transfer,
            filterProgress: remaining === 0 ? 1 : Math.min(0.99, state.filterProgress + elapsed / 5)
        });
    }
}
export function drawApparatus(ctx, cx, cy, state) {
    if (state.stirringUntil > performance.now() && state.currentLiquidVol > 0) {
        const swing = Math.sin(performance.now() / 150) * 11;
        ctx.save();
        ctx.lineCap = 'round';
        ctx.strokeStyle = '#9aafbc';
        ctx.lineWidth = 6;
        ctx.beginPath();
        ctx.moveTo(cx + swing + 18, cy - 165);
        ctx.lineTo(cx - swing, cy + 78);
        ctx.stroke();
        ctx.strokeStyle = 'rgba(255,255,255,.8)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();
    }
    if (state.pipetteAmount > 0) {
        ctx.save();
        const x = cx + 118;
        const y = cy - 132;
        ctx.fillStyle = '#44596b';
        ctx.beginPath();
        ctx.ellipse(x, y - 16, 14, 18, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = config.hexToRgbA(state.liquidColor, 0.8);
        ctx.fillRect(x - 4, y + 72, 8, 30);
        ctx.strokeStyle = '#78909d';
        ctx.lineWidth = 2;
        ctx.strokeRect(x - 5, y, 10, 100);
        ctx.beginPath();
        ctx.moveTo(x - 5, y + 100);
        ctx.lineTo(x, y + 115);
        ctx.lineTo(x + 5, y + 100);
        ctx.stroke();
        ctx.restore();
    }
    if (state.filterProgress > 0) {
        const x = cx + 145;
        const top = cy - 52;
        ctx.save();
        ctx.strokeStyle = '#78909d';
        ctx.lineWidth = 3;
        ctx.fillStyle = 'rgba(210,230,239,.18)';
        ctx.beginPath();
        ctx.moveTo(x - 40, top);
        ctx.lineTo(x - 7, top + 62);
        ctx.lineTo(x - 7, top + 86);
        ctx.lineTo(x + 7, top + 86);
        ctx.lineTo(x + 7, top + 62);
        ctx.lineTo(x + 40, top);
        ctx.stroke();
        ctx.fill();
        ctx.fillStyle = '#f5f1e7';
        ctx.beginPath();
        ctx.moveTo(x - 34, top + 4);
        ctx.lineTo(x, top + 59);
        ctx.lineTo(x + 34, top + 4);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = state.precipitateColor || '#ddd';
        ctx.beginPath();
        ctx.ellipse(x, top + 40, 12, 5, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = config.hexToRgbA(state.liquidColor, 0.6);
        ctx.fillRect(x - 25, cy + 105 - Math.min(state.filteredLiquidVol, 65), 50, Math.min(state.filteredLiquidVol, 65));
        ctx.strokeStyle = '#78909d';
        ctx.beginPath();
        ctx.moveTo(x - 30, cy + 24);
        ctx.lineTo(x - 30, cy + 106);
        ctx.lineTo(x + 30, cy + 106);
        ctx.lineTo(x + 30, cy + 24);
        ctx.stroke();
        if (state.filterProgress < 1) {
            ctx.strokeStyle = config.hexToRgbA(state.liquidColor, 0.7);
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(x, top + 86);
            ctx.lineTo(x, cy + 25);
            ctx.stroke();
        }
        ctx.restore();
    }
}
//# sourceMappingURL=apparatus.js.map