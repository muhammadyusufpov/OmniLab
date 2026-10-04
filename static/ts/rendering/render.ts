import * as config from '../configuration/config.js';

export function updateAndDrawAmbientBubbles(cx: number, cy: number): void {
    if (!config.getLabState().burnerActive) {
        config.updateLabState({ ambientBubbles: [] });
        return;
    }

    const state = config.getLabState();

    if (state.currentLiquidVol <= 0) {
        config.updateLabState({ ambientBubbles: [] });
        return;
    }

    let vesselWidth = 180;
    if (state.currentVessel === 'tube') vesselWidth = 70;

    let spawnChance = state.burnerActive ? 0.65 : 0.15;
    let maxBubbles = state.burnerActive ? 90 : 30;

    let bubbles = [...state.ambientBubbles];

    if (Math.random() < spawnChance && bubbles.length < maxBubbles) {
        let span = vesselWidth - 20;
        if (state.currentVessel === 'flask') span = 140;
        
        bubbles.push({
            x: cx + (Math.random() * span - span / 2),
            y: cy + 110,
            vx: 0,
            vy: 0,
            alpha: 1,
            color: '#ffffff',
            r: state.burnerActive ? Math.random() * 5 + 2 : Math.random() * 3 + 1.5,
            speed: state.burnerActive ? Math.random() * 3.5 + 2 : Math.random() * 1 + 0.5,
            wobble: Math.random() * 2,
            wobbleSpeed: state.burnerActive ? Math.random() * 0.3 + 0.15 : Math.random() * 0.1 + 0.05
        } as any);
    }

    for (let i = bubbles.length - 1; i >= 0; i--) {
        let b = bubbles[i] as any;
        b.y -= b.speed;
        b.wobble += b.wobbleSpeed;
        let currentX = b.x + Math.sin(b.wobble) * (state.burnerActive ? 2.5 : 1.5);

        let liquidTopY = cy + 120 - state.currentLiquidVol + Math.sin(currentX * 0.025 + state.waveTime) * 4.5;

        let inside = false;
        if (state.currentVessel === 'beaker' && Math.abs(currentX - cx) < 85) inside = true;
        else if (state.currentVessel === 'tube' && Math.abs(currentX - cx) < 30) inside = true;
        else if (state.currentVessel === 'flask') {
            let currentLiquidHeight = (cy + 120) - b.y;
            let ratio = currentLiquidHeight / 220;
            let maxW = 220 - (220 - 50) * ratio;
            if (Math.abs(currentX - cx) < (maxW / 2 - 10)) inside = true;
        }

        if (b.y < liquidTopY || !inside) {
            bubbles.splice(i, 1);
            continue;
        }

        if (config.ctx) {
            config.ctx.fillStyle = state.burnerActive ? 'rgba(255, 255, 255, 0.75)' : 'rgba(255, 255, 255, 0.5)';
            config.ctx.beginPath();
            config.ctx.arc(currentX, b.y, b.r, 0, Math.PI * 2);
            config.ctx.fill();
        }
    }

    config.updateLabState({ ambientBubbles: bubbles });
}

function drawPrecipitate(
    cx: number,
    liquidTopY: number,
    liquidBottomY: number,
    startX: number,
    endX: number,
    color: string
): void {
    if (!config.ctx) return;

    const width = Math.max(20, endX - startX - 18);
    const height = Math.max(16, liquidBottomY - liquidTopY - 8);
    config.ctx.save();
    config.ctx.shadowColor = config.hexToRgbA(color, 0.3);
    config.ctx.shadowBlur = 2;

    for (let index = 0; index < 42; index++) {
        const x = startX + 9 + ((index * 37) % width);
        const depth = ((index * 29) % height) / height;
        const y = liquidBottomY - 6 - depth * height * 0.82;
        const radiusX = 2.2 + (index % 4) * 0.65;
        const radiusY = 1.4 + (index % 3) * 0.45;

        config.ctx.fillStyle = config.hexToRgbA(
            color,
            0.58 + (index % 3) * 0.1
        );
        config.ctx.strokeStyle = color === '#f5f3ea'
            ? 'rgba(70, 83, 96, 0.28)'
            : config.hexToRgbA(color, 0.82);
        config.ctx.lineWidth = 0.8;
        config.ctx.beginPath();
        config.ctx.ellipse(x, y, radiusX, radiusY, 0, 0, Math.PI * 2);
        config.ctx.fill();
        config.ctx.stroke();
    }

    const sedimentHeight = Math.min(13, Math.max(6, height * 0.12));
    const sedimentGradient = config.ctx.createLinearGradient(
        cx,
        liquidBottomY - sedimentHeight,
        cx,
        liquidBottomY
    );
    sedimentGradient.addColorStop(0, config.hexToRgbA(color, 0.15));
    sedimentGradient.addColorStop(1, config.hexToRgbA(color, 0.78));
    config.ctx.fillStyle = sedimentGradient;
    config.ctx.fillRect(
        startX,
        liquidBottomY - sedimentHeight,
        endX - startX,
        sedimentHeight
    );
    config.ctx.restore();
}

let currentRenderColor: string | null = null;
let thermalBlastTimer: ReturnType<typeof setInterval> | null = null;

export function cancelReactionEffects(): void {
    if (thermalBlastTimer !== null) {
        clearInterval(thermalBlastTimer);
        thermalBlastTimer = null;
    }
    currentRenderColor = null;
}

export function drawVesselAndFluid(): void {
    if (!config.canvas || !config.ctx) return;

    config.ctx.clearRect(0, 0, config.canvas.width, config.canvas.height);
    
    const state = config.getLabState();
    const cx = config.canvas.width / 2 + state.vesselOffsetX;
    let cy = config.canvas.height / 2 + 50 + state.vesselOffsetY;

    const updatedState = config.getLabState();
    let targetColor = updatedState.liquidColor;
    
    if (updatedState.burnerActive) {
        targetColor = '#eab308'; 
    }

    if (!currentRenderColor) {
        currentRenderColor = updatedState.liquidColor;
    }

    let match1 = config.hexToRgbA(currentRenderColor, 1).match(/\d+/g);
    let match2 = config.hexToRgbA(targetColor, 1).match(/\d+/g);

    let c1 = match1 ? match1.map(Number) : [255, 255, 255];
    let c2 = match2 ? match2.map(Number) : [255, 255, 255];
    
    let r = Math.round(c1[0] + (c2[0] - c1[0]) * 0.18);
    let g = Math.round(c1[1] + (c2[1] - c1[1]) * 0.18);
    let b = Math.round(c1[2] + (c2[2] - c1[2]) * 0.18);
    
    // Keep a hex color so the translucent glass shading uses the real liquid color.
    currentRenderColor = `#${[r, g, b].map(channel => channel.toString(16).padStart(2, '0')).join('')}`;

    if (updatedState.streamActive && Number.isFinite(updatedState.streamX)) {
        config.ctx.save();
        config.ctx.beginPath();
        const streamGradient = config.ctx.createLinearGradient(updatedState.streamX - 4, 0, updatedState.streamX + 4, 0);
        streamGradient.addColorStop(0, config.hexToRgbA(updatedState.streamColor, 0.55));
        streamGradient.addColorStop(0.5, updatedState.streamColor);
        streamGradient.addColorStop(1, config.hexToRgbA(updatedState.streamColor, 0.8));
        config.ctx.strokeStyle = streamGradient;
        config.ctx.lineWidth = 5;
        config.ctx.lineCap = 'round';
        let baseLevel = updatedState.currentVessel === 'tube' ? cy + 104 : cy + 106;
        if (updatedState.burnerActive) {
            baseLevel -= 40;
        }
        let liquidTopY = baseLevel - updatedState.currentLiquidVol;
        const streamStartX = Math.max(12, Math.min(config.canvas.width - 12, updatedState.streamX));
        const impactX = cx + Math.sin(updatedState.waveTime * 2) * 2;
        config.ctx.moveTo(streamStartX, 8);
        config.ctx.bezierCurveTo(streamStartX, liquidTopY * 0.35, impactX - 10, liquidTopY * 0.7, impactX, liquidTopY);
        config.ctx.stroke();
        config.ctx.restore();
    }

    if (updatedState.burnerActive) {
        cy = cy - 40;
        const burnerY = cy + 110;
        
        config.ctx.save();
        let wobble = Math.sin(updatedState.waveTime * 1.8) * 2.5;
        let flameHeight = 65 + Math.sin(updatedState.waveTime * 3.6) * 4 + Math.random() * 4;
    
        config.ctx.globalCompositeOperation = 'screen';
    
        config.ctx.beginPath();
        config.ctx.moveTo(cx - 16, burnerY);
        config.ctx.bezierCurveTo(cx - 22, burnerY - 15, cx + wobble - 25, burnerY - flameHeight + 20, cx + wobble, burnerY - flameHeight);
        config.ctx.bezierCurveTo(cx + wobble + 25, burnerY - flameHeight + 20, cx + 22, burnerY - 15, cx + 16, burnerY);
        
        let outerGrad = config.ctx.createRadialGradient(cx + wobble/2, burnerY - flameHeight/2, 5, cx + wobble/2, burnerY - flameHeight/2, flameHeight/2);
        outerGrad.addColorStop(0, 'rgba(255, 90, 0, 0.8)');
        outerGrad.addColorStop(0.4, 'rgba(255, 130, 0, 0.4)');
        outerGrad.addColorStop(1, 'rgba(255, 60, 0, 0)');
        config.ctx.fillStyle = outerGrad;
        config.ctx.fill();
    
        config.ctx.beginPath();
        config.ctx.moveTo(cx - 11, burnerY);
        config.ctx.bezierCurveTo(cx - 14, burnerY - 10, cx + wobble - 15, burnerY - flameHeight + 25, cx + wobble, burnerY - flameHeight + 15);
        config.ctx.bezierCurveTo(cx + wobble + 15, burnerY - flameHeight + 25, cx + 11, burnerY - 10, cx + 11, burnerY);
        
        let midGrad = config.ctx.createLinearGradient(cx, burnerY, cx + wobble, burnerY - flameHeight);
        midGrad.addColorStop(0, 'rgba(255, 170, 0, 0.9)');
        midGrad.addColorStop(0.5, 'rgba(255, 220, 50, 0.7)');
        midGrad.addColorStop(1, 'rgba(255, 255, 150, 0)'); midGrad.addColorStop(1, 'rgba(255, 255, 150, 0)');
        config.ctx.fillStyle = midGrad;
        config.ctx.fill();
    
        config.ctx.beginPath();
        config.ctx.moveTo(cx - 7, burnerY);
        config.ctx.bezierCurveTo(cx - 9, burnerY - 5, cx + wobble - 8, burnerY - 30, cx + wobble * 0.4, burnerY - 38);
        config.ctx.bezierCurveTo(cx + wobble + 8, burnerY - 30, cx + 7, burnerY - 5, cx + 7, burnerY);
        
        let innerGrad = config.ctx.createLinearGradient(cx, burnerY, cx, burnerY - 38);
        innerGrad.addColorStop(0, 'rgba(0, 100, 255, 0.95)');
        innerGrad.addColorStop(0.5, 'rgba(0, 200, 255, 0.7)');
        innerGrad.addColorStop(1, 'rgba(150, 240, 255, 0)');
        config.ctx.fillStyle = innerGrad;
        config.ctx.fill();
    
        config.ctx.restore();
        
        config.ctx.save();
        config.ctx.shadowBlur = 6;
        config.ctx.shadowColor = 'rgba(0,0,0,0.15)';
        
        let tubeGrad = config.ctx.createLinearGradient(cx - 10, 0, cx + 10, 0);
        tubeGrad.addColorStop(0, '#4a5568');
        tubeGrad.addColorStop(0.3, '#718096');
        tubeGrad.addColorStop(0.7, '#a0aec0');
        tubeGrad.addColorStop(1, '#2d3748');
        config.ctx.fillStyle = tubeGrad;
        config.ctx.fillRect(cx - 10, burnerY, 20, 60);
        
        config.ctx.fillStyle = updatedState.burnerActive ? '#22c55e' : '#ef4444';
        config.ctx.beginPath();
        config.ctx.arc(cx, burnerY + 48, 6, 0, Math.PI * 2);
        config.ctx.fill();
        config.ctx.strokeStyle = '#ffffff';
        config.ctx.lineWidth = 1.5;
        config.ctx.stroke();
        
        let baseGrad = config.ctx.createLinearGradient(cx - 35, 0, cx + 35, 0);
        baseGrad.addColorStop(0, '#1a202c');
        baseGrad.addColorStop(0.5, '#4a5568');
        baseGrad.addColorStop(1, '#1a202c');
        config.ctx.fillStyle = baseGrad;
        config.ctx.fillRect(cx - 35, burnerY + 60, 70, 12);
        
        config.ctx.strokeStyle = '#718096';
        config.ctx.lineWidth = 4;
        config.ctx.beginPath();
        config.ctx.moveTo(cx - 60, cy + 108);
        config.ctx.lineTo(cx + 60, cy + 108);
        config.ctx.stroke();
        
        config.ctx.restore();
    } else {
        config.ctx.save();
        config.ctx.beginPath();
        let shadowWidth = updatedState.currentVessel === 'flask' ? 120 : (updatedState.currentVessel === 'beaker' ? 100 : 45);
        config.ctx.ellipse(cx, cy + 110, shadowWidth, 10, 0, 0, Math.PI * 2);
        config.ctx.fillStyle = updatedState.theme === 'dark' ? 'rgba(0, 0, 0, 0.3)' : 'rgba(0, 0, 0, 0.06)';
        config.ctx.fill();
        config.ctx.restore();
    }

    if (updatedState.currentLiquidVol > 0) {
        config.ctx.save();
        config.ctx.beginPath();
        
        let startX = cx;
        let endX = cx;

        if (updatedState.currentVessel === 'beaker') {
            startX = cx - 86;
            endX = cx + 86;
            config.ctx.moveTo(cx - 86, cy - 70);
            config.ctx.lineTo(cx - 86, cy + 95);
            config.ctx.arcTo(cx - 86, cy + 108, cx - 72, cy + 108, 12);
            config.ctx.lineTo(cx + 72, cy + 108);
            config.ctx.arcTo(cx + 86, cy + 108, cx + 86, cy + 95, 12);
            config.ctx.lineTo(cx + 86, cy - 70);
        } else if (updatedState.currentVessel === 'tube') {
            startX = cx - 33;
            endX = cx + 33;
            config.ctx.moveTo(cx - 33, cy - 90);
            config.ctx.lineTo(cx - 33, cy + 75);
            config.ctx.arc(cx, cy + 75, 33, Math.PI, 0, true);
            config.ctx.lineTo(cx + 33, cy - 90);
        } else if (updatedState.currentVessel === 'flask') {
            startX = cx - 106;
            endX = cx + 106;
            config.ctx.moveTo(cx - 23, cy - 90);
            config.ctx.lineTo(cx - 23, cy - 30);
            config.ctx.lineTo(cx - 106, cy + 100);
            config.ctx.arcTo(cx - 110, cy + 108, cx - 95, cy + 108, 12);
            config.ctx.lineTo(cx + 95, cy + 108);
            config.ctx.arcTo(cx + 110, cy + 108, cx + 106, cy + 100, 12);
            config.ctx.lineTo(cx + 23, cy - 30);
            config.ctx.lineTo(cx + 23, cy - 90);
        }
        config.ctx.closePath();
        config.ctx.clip();

        let liquidGrad = config.ctx.createLinearGradient(cx - 110, 0, cx + 110, 0);
        liquidGrad.addColorStop(0, config.hexToRgbA(currentRenderColor, 0.85));
        liquidGrad.addColorStop(0.3, config.hexToRgbA(currentRenderColor, 0.95));
        liquidGrad.addColorStop(0.7, currentRenderColor);
        liquidGrad.addColorStop(1, config.hexToRgbA(currentRenderColor, 0.7));
        
        config.ctx.fillStyle = liquidGrad;
        config.ctx.beginPath();
        let baseLevel = updatedState.currentVessel === 'tube' ? cy + 104 : cy + 106;
        
        let liquidTopY = baseLevel - updatedState.currentLiquidVol;
        let amplitude = updatedState.burnerActive ? 6 : (updatedState.streamActive ? 5.5 : 1.4);
        
        config.ctx.moveTo(startX - 10, liquidTopY);
        
        for (let x = startX - 10; x <= endX + 10; x++) {
            let waveY = liquidTopY + Math.sin(x * 0.05 + updatedState.waveTime * 1.3) * amplitude;
            config.ctx.lineTo(x, waveY);
        }
        
        if (updatedState.currentVessel === 'beaker') {
            config.ctx.lineTo(cx + 100, cy + 130);
            config.ctx.lineTo(cx - 100, cy + 130);
        } else if (updatedState.currentVessel === 'tube') {
            config.ctx.lineTo(cx + 50, cy + 130);
            config.ctx.lineTo(cx - 50, cy + 130);
        } else if (updatedState.currentVessel === 'flask') {
            config.ctx.lineTo(cx + 130, cy + 130);
            config.ctx.lineTo(cx - 130, cy + 130);
        }
        
        config.ctx.closePath();
        config.ctx.fill();

        if (updatedState.streamActive) {
            const rippleWidth = updatedState.currentVessel === 'tube' ? 16 : 28;
            config.ctx.strokeStyle = 'rgba(255, 255, 255, 0.58)';
            config.ctx.lineWidth = 1.5;
            for (let ripple = 0; ripple < 2; ripple++) {
                const spread = rippleWidth * (0.5 + ripple * 0.45);
                config.ctx.beginPath();
                config.ctx.ellipse(cx, liquidTopY + 1 + ripple * 2, spread, 2.5, 0, 0, Math.PI);
                config.ctx.stroke();
            }
        }

        if (updatedState.precipitateColor) {
            drawPrecipitate(
                cx,
                liquidTopY,
                baseLevel,
                startX,
                endX,
                updatedState.precipitateColor
            );
        }

        if (updatedState.burnerActive) {
            let topY = baseLevel - updatedState.currentLiquidVol;
            config.ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
            for (let i = 0; i < 15; i++) {
                let fx = cx + (Math.random() - 0.5) * (updatedState.currentVessel === 'tube' ? 50 : 130);
                let fy = topY + (Math.random() * 14 - 7);
                config.ctx.beginPath();
                config.ctx.arc(fx, fy, Math.random() * 4 + 2, 0, Math.PI * 2);
                config.ctx.fill();
            }
        }

        updateAndDrawAmbientBubbles(cx, cy);
        config.ctx.restore();
    }

    let glassGrad = config.ctx.createLinearGradient(cx - 120, 0, cx + 120, 0);
    if (updatedState.theme === 'dark') {
        glassGrad.addColorStop(0, 'rgba(255, 255, 255, 0.35)');
        glassGrad.addColorStop(0.1, 'rgba(255, 255, 255, 0.12)');
        glassGrad.addColorStop(0.4, 'rgba(255, 255, 255, 0.01)');
        glassGrad.addColorStop(0.9, 'rgba(255, 255, 255, 0.12)');
        glassGrad.addColorStop(1, 'rgba(255, 255, 255, 0.35)');
        config.ctx.strokeStyle = 'rgba(210, 225, 240, 0.5)';
    } else {
        glassGrad.addColorStop(0, 'rgba(150, 175, 200, 0.25)');
        glassGrad.addColorStop(0.1, 'rgba(180, 200, 220, 0.08)');
        glassGrad.addColorStop(0.4, 'rgba(255, 255, 255, 0.01)');
        glassGrad.addColorStop(0.9, 'rgba(180, 200, 220, 0.08)');
        glassGrad.addColorStop(1, 'rgba(150, 175, 200, 0.25)');
        config.ctx.strokeStyle = 'rgba(70, 90, 110, 0.4)';
    }

    config.ctx.fillStyle = glassGrad;
    config.ctx.lineWidth = 3.5;
    config.ctx.lineCap = 'round';
    config.ctx.lineJoin = 'round';

    config.ctx.beginPath();
    if (updatedState.currentVessel === 'beaker') {
        config.ctx.moveTo(cx - 88, cy - 80);
        config.ctx.lineTo(cx - 88, cy + 96);
        config.ctx.arcTo(cx - 88, cy + 108, cx - 72, cy + 108, 14);
        config.ctx.lineTo(cx + 72, cy + 108);
        config.ctx.arcTo(cx + 88, cy + 108, cx + 88, cy + 96, 14);
        config.ctx.lineTo(cx + 88, cy - 80);
        config.ctx.stroke();
        config.ctx.fill();

        config.ctx.beginPath();
        config.ctx.ellipse(cx, cy - 80, 88, 10, 0, 0, Math.PI * 2);
        config.ctx.stroke();
    } else if (updatedState.currentVessel === 'tube') {
        config.ctx.moveTo(cx - 35, cy - 100);
        config.ctx.lineTo(cx - 35, cy + 73);
        config.ctx.arc(cx, cy + 73, 35, Math.PI, 0, true);
        config.ctx.lineTo(cx + 35, cy - 100);
        config.ctx.stroke();
        config.ctx.fill();

        config.ctx.beginPath();
        config.ctx.ellipse(cx, cy - 100, 35, 7, 0, 0, Math.PI * 2);
        config.ctx.stroke();
    } else if (updatedState.currentVessel === 'flask') {
        config.ctx.moveTo(cx - 25, cy - 100);
        config.ctx.lineTo(cx - 25, cy - 30);
        config.ctx.lineTo(cx - 108, cy + 98);
        config.ctx.arcTo(cx - 112, cy + 108, cx - 98, cy + 108, 14);
        config.ctx.lineTo(cx + 98, cy + 108);
        config.ctx.arcTo(cx + 112, cy + 108, cx + 108, cy + 98, 14);
        config.ctx.lineTo(cx + 25, cy - 30);
        config.ctx.lineTo(cx + 25, cy - 100);
        config.ctx.closePath();
        config.ctx.stroke();
        config.ctx.fill();

        config.ctx.beginPath();
        config.ctx.ellipse(cx, cy - 100, 25, 5, 0, 0, Math.PI * 2);
        config.ctx.stroke();
    }

    config.ctx.fillStyle = 'rgba(255, 255, 255, 0.45)';
    config.ctx.beginPath();
    if (updatedState.currentVessel === 'beaker') {
        config.ctx.ellipse(cx - 74, cy + 10, 4, 70, 0.02, 0, Math.PI * 2);
    } else if (updatedState.currentVessel === 'tube') {
        config.ctx.ellipse(cx - 25, cy - 10, 3, 60, 0.01, 0, Math.PI * 2);
    } else if (updatedState.currentVessel === 'flask') {
        config.ctx.ellipse(cx - 68, cy + 50, 5, 35, 0.45, 0, Math.PI * 2);
    }
    config.ctx.fill();
}

export function triggerThermalBlast(): void {
    cancelReactionEffects();
    let iteration = 0;
    thermalBlastTimer = setInterval(() => {
        if (!config.ctx || !config.canvas) return;
        config.ctx.fillStyle = iteration % 2 === 0 ? 'rgba(255, 61, 61, 0.85)' : 'rgba(255, 213, 0, 0.85)';
        config.ctx.beginPath();
        config.ctx.arc(config.canvas.width / 2, config.canvas.height / 2 + 80, 80 + (iteration * 16), 0, Math.PI * 2);
        config.ctx.fill();
        iteration++;
        if(iteration > 12) {
            if (thermalBlastTimer !== null) {
                clearInterval(thermalBlastTimer);
                thermalBlastTimer = null;
            }
            config.updateLabState({ liquidColor: '#424242' });
            drawVesselAndFluid();
        }
    }, 80);
}

export function triggerSmokeEffect(): void {
    console.log("Smoke effect triggered");
}

export function renderChemicalVessel(app: any): void {
    const ctx = config.ctx;
    if (!ctx) return;
    const cx = app.x;
    const cy = app.y;
    const state = config.getLabState();

    ctx.save();
    
    let width = 120, height = 160;
    if (app.type === 'beaker') { width = 110; height = 140; }
    if (app.type === 'tube') { width = 40; height = 150; }

    if (state.currentLiquidVol > 0) {
        ctx.fillStyle = state.liquidColor || 'rgba(74, 222, 128, 0.6)';
        ctx.beginPath();
        if (app.type === 'flask') {
            ctx.moveTo(cx - width/2 + 10, cy + height/2 - 5);
            ctx.lineTo(cx + width/2 - 10, cy + height/2 - 5);
            ctx.lineTo(cx + width/3, cy + 10);
            ctx.lineTo(cx - width/3, cy + 10);
        } else if (app.type === 'beaker') {
            ctx.rect(cx - width/2 + 5, cy - height/4, width - 10, height/2 + 35);
        } else if (app.type === 'tube') {
            ctx.rect(cx - width/2 + 4, cy - height/4, width - 8, height/2 + 35);
        }
        ctx.fill();

        if (state.isBubbling) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
            for (let i = 0; i < 10; i++) {
                let bx = cx + (Math.random() - 0.5) * (width - 30);
                let by = cy + (Math.random() * 40);
                ctx.beginPath();
                ctx.arc(bx, by, Math.random() * 4 + 1, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    ctx.lineWidth = 4;
    ctx.strokeStyle = state.theme === 'dark' ? '#ffffff' : '#1e293b';
    ctx.beginPath();

    if (app.type === 'flask') {
        ctx.moveTo(cx - 20, cy - height/2);
        ctx.lineTo(cx + 20, cy - height/2);
        ctx.lineTo(cx + 20, cy - height/4);
        ctx.lineTo(cx + width/2, cy + height/2);
        ctx.lineTo(cx - width/2, cy + height/2);
        ctx.lineTo(cx - 20, cy - height/4);
        ctx.closePath();
    } else if (app.type === 'beaker') {
        ctx.moveTo(cx - width/2, cy - height/2);
        ctx.lineTo(cx - width/2, cy + height/2);
        ctx.lineTo(cx + width/2, cy + height/2);
        ctx.lineTo(cx + width/2, cy - height/2);
    } else if (app.type === 'tube') {
        ctx.moveTo(cx - width/2, cy - height/2);
        ctx.lineTo(cx - width/2, cy + height/2 - 10);
        ctx.arc(cx, cy + height/2 - 10, width/2, Math.PI, 0, true);
        ctx.lineTo(cx + width/2, cy - height/2);
    }

    ctx.stroke();
    ctx.restore();
}
