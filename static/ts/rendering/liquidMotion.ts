import type { LabState } from '../configuration/config.js';

type LiquidMotion = Pick<LabState,
    'liquidTilt' | 'liquidTiltVelocity' | 'liquidRipple' | 'liquidRippleVelocity'>;

const clamp = (value: number, limit: number): number =>
    Math.max(-limit, Math.min(limit, value));

export function moveLiquid(
    state: LiquidMotion,
    dx: number,
    dy: number
): LiquidMotion {
    return {
        liquidTilt: state.liquidTilt,
        liquidTiltVelocity: clamp(state.liquidTiltVelocity - dx * 2.4, 85),
        liquidRipple: state.liquidRipple,
        liquidRippleVelocity: clamp(
            state.liquidRippleVelocity + Math.hypot(dx, dy) * 1.4,
            90
        )
    };
}

function settle(position: number, velocity: number, elapsed: number, spring: number, damping: number): [number, number] {
    const nextVelocity = velocity + (-spring * position - damping * velocity) * elapsed;
    const nextPosition = position + nextVelocity * elapsed;
    return Math.abs(nextPosition) < 0.04 && Math.abs(nextVelocity) < 0.3
        ? [0, 0]
        : [nextPosition, nextVelocity];
}

export function settleLiquid(state: LiquidMotion, elapsed: number): LiquidMotion {
    const step = Math.min(Math.max(elapsed, 0), 0.05);
    const [liquidTilt, liquidTiltVelocity] = settle(
        state.liquidTilt, state.liquidTiltVelocity, step, 70, 6.5
    );
    const [liquidRipple, liquidRippleVelocity] = settle(
        state.liquidRipple, state.liquidRippleVelocity, step, 105, 7.5
    );
    return {
        liquidTilt: clamp(liquidTilt, 16),
        liquidTiltVelocity,
        liquidRipple: clamp(liquidRipple, 8),
        liquidRippleVelocity
    };
}

export function liquidSurfaceDisplacement(
    state: LiquidMotion,
    x: number,
    centerX: number,
    halfWidth: number,
    waveTime: number
): number {
    const position = clamp((x - centerX) / halfWidth, 1);
    return state.liquidTilt * position
        + state.liquidRipple * Math.sin(position * Math.PI * 1.5 + waveTime * 3);
}
