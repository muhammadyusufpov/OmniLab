import * as config from '../configuration/config.js';
import { pourIntoLiquid } from '../rendering/liquidMotion.js';

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

function announce(message: string): void {
    const status = document.getElementById('apparatus-status');
    if (status) status.textContent = message;
}

export function syncAccessoryButtons(): void {
    const state = config.getLabState();
    const selected: Record<string, boolean> = {
        'tool-tripod': state.tripodActive,
        'tool-clamp': state.clampActive,
        'tool-watch-glass': state.watchGlassActive,
        'opt-burner': state.burnerActive
    };
    for (const [id, active] of Object.entries(selected)) {
        const button = document.getElementById(id);
        if (active) button?.classList.add('selected');
        else button?.classList.remove('selected');
        button?.setAttribute('aria-pressed', String(active));
    }
}

function toggleAccessory(type: 'tripod' | 'clamp' | 'watch-glass'): void {
    const state = config.getLabState();
    if (!state.apparatusSelected) {
        announce('Choose a vessel first, then add compatible equipment.');
        return;
    }
    if (state.filterProgress > 0) {
        announce('Reset the setup before changing equipment after filtration.');
        return;
    }
    if (type === 'tripod') {
        if (state.currentVessel !== 'beaker' && state.currentVessel !== 'flask') {
            announce('A tripod and gauze support a beaker or flask here. Choose one first.');
            return;
        }
        config.updateLabState({ tripodActive: !state.tripodActive, burnerActive: state.tripodActive ? false : state.burnerActive });
        announce(state.tripodActive ? 'Tripod removed. The burner is off.' : 'Tripod and wire gauze support the vessel. Add a burner only if needed.');
    } else if (type === 'clamp') {
        if (state.currentVessel !== 'tube' && state.currentVessel !== 'cylinder') {
            announce('The clamp stand holds a test tube or graduated cylinder here.');
            return;
        }
        config.updateLabState({ clampActive: !state.clampActive });
        announce(state.clampActive ? 'Clamp stand removed.' : 'Clamp stand holds the vessel. It does not measure or change a reaction.');
    } else {
        if (state.currentVessel !== 'beaker') {
            announce('The watch glass cover fits the beaker only.');
            return;
        }
        if (state.burnerActive) {
            announce('Turn the burner off before adding the watch glass cover.');
            return;
        }
        config.updateLabState({
            watchGlassActive: !state.watchGlassActive,
            stirringUntil: state.watchGlassActive ? state.stirringUntil : 0
        });
        announce(state.watchGlassActive ? 'Watch glass cover removed.' : 'Watch glass covers the beaker. It is a visual setup aid.');
    }
    syncAccessoryButtons();
}

function syncPipetteButton(loaded: boolean): void {
    const button = document.getElementById('tool-pipette');
    if (!button) return;
    button.textContent = loaded ? 'Return pipette sample' : 'Pipette sample';
    button.setAttribute('aria-pressed', String(loaded));
}

function usePipette(): void {
    const state = config.getLabState();
    if (state.watchGlassActive) {
        announce('Remove the watch glass cover before using the pipette.');
        return;
    }
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
    } else if (state.currentLiquidVol >= 12 && state.targetLiquidVol >= 12) {
        config.updateLabState({
            pipetteAmount: 12,
            targetLiquidVol: state.targetLiquidVol - 12
        });
        syncPipetteButton(true);
        announce('The pipette holds a small sample. Select it again to return the liquid. The volume is not calibrated.');
    } else {
        announce('Add a chemical before using the pipette.');
    }
}

function stir(): void {
    const state = config.getLabState();
    if (state.watchGlassActive) {
        announce('Remove the watch glass cover before stirring.');
        return;
    }
    if (state.currentLiquidVol <= 0 || state.filterProgress > 0) {
        announce('Add liquid to a vessel before stirring.');
        return;
    }
    config.updateLabState({ stirringUntil: reducedMotion.matches ? 0 : performance.now() + 2600 });
    announce('The glass rod stirs the liquid. Stirring does not change the predicted reaction.');
}

function filter(): void {
    const state = config.getLabState();
    if (state.watchGlassActive) {
        announce('Remove the watch glass cover before filtering.');
        return;
    }
    if (state.burnerActive) {
        announce('Turn the burner off before using filter paper.');
        return;
    }
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

export function bindApparatusTools(): void {
    const actions: Record<string, () => void> = {
        'tool-tripod': () => toggleAccessory('tripod'),
        'tool-clamp': () => toggleAccessory('clamp'),
        'tool-watch-glass': () => toggleAccessory('watch-glass'),
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
        syncAccessoryButtons();
        announce('Combine compatible equipment around one vessel. Heat and volumes are not measured. Results are educational estimates.');
    });
}

export function updateApparatus(now: number, elapsed: number): void {
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

export function drawApparatus(ctx: CanvasRenderingContext2D, cx: number, cy: number, state: config.LabState): void {
    const metal = state.theme === 'dark' ? '#a9bac8' : '#66798a';
    if (state.tripodActive) {
        ctx.save();
        ctx.strokeStyle = metal;
        ctx.lineWidth = 5;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(cx - 87, cy + 114);
        ctx.lineTo(cx - 112, cy + 215);
        ctx.moveTo(cx + 87, cy + 114);
        ctx.lineTo(cx + 112, cy + 215);
        ctx.moveTo(cx - 15, cy + 116);
        ctx.lineTo(cx + 13, cy + 214);
        ctx.stroke();
        ctx.strokeStyle = '#87959d';
        ctx.lineWidth = 7;
        ctx.beginPath();
        ctx.moveTo(cx - 103, cy + 112);
        ctx.lineTo(cx + 103, cy + 112);
        ctx.stroke();
        ctx.strokeStyle = 'rgba(80,99,110,.55)';
        ctx.lineWidth = 1;
        for (let offset = -90; offset <= 90; offset += 12) {
            ctx.beginPath();
            ctx.moveTo(cx + offset, cy + 108);
            ctx.lineTo(cx + offset + 7, cy + 116);
            ctx.stroke();
        }
        ctx.restore();
    }

    if (state.clampActive) {
        ctx.save();
        const x = cx + 94;
        ctx.strokeStyle = metal;
        ctx.lineWidth = 5;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(x, cy + 108);
        ctx.lineTo(x, cy - 155);
        ctx.moveTo(x - 44, cy + 108);
        ctx.lineTo(x + 44, cy + 108);
        ctx.moveTo(x, cy - 70);
        ctx.lineTo(cx + 31, cy - 70);
        ctx.stroke();
        ctx.fillStyle = '#576b7b';
        ctx.beginPath();
        ctx.arc(x, cy - 70, 7, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    if (state.watchGlassActive) {
        ctx.save();
        ctx.fillStyle = 'rgba(176,210,224,.25)';
        ctx.strokeStyle = metal;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(cx, cy - 83, 90, 12, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(cx, cy - 92, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
    }

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
