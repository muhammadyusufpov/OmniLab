const clamp = (value, limit) => Math.max(-limit, Math.min(limit, value));
export function moveLiquid(state, dx, dy) {
    return {
        liquidTilt: state.liquidTilt,
        liquidTiltVelocity: clamp(state.liquidTiltVelocity - dx * 2.4, 85),
        liquidRipple: state.liquidRipple,
        liquidRippleVelocity: clamp(state.liquidRippleVelocity + Math.hypot(dx, dy) * 1.4, 90)
    };
}
export function pourIntoLiquid(state) {
    return {
        liquidTilt: state.liquidTilt,
        liquidTiltVelocity: clamp(state.liquidTiltVelocity + 24, 85),
        liquidRipple: state.liquidRipple,
        liquidRippleVelocity: clamp(state.liquidRippleVelocity + 65, 90)
    };
}
function settle(position, velocity, elapsed, spring, damping) {
    const nextVelocity = velocity + (-spring * position - damping * velocity) * elapsed;
    const nextPosition = position + nextVelocity * elapsed;
    return Math.abs(nextPosition) < 0.02 && Math.abs(nextVelocity) < 0.15
        ? [0, 0]
        : [nextPosition, nextVelocity];
}
export function settleLiquid(state, elapsed) {
    const step = Math.min(Math.max(elapsed, 0), 0.05);
    const [liquidTilt, liquidTiltVelocity] = settle(state.liquidTilt, state.liquidTiltVelocity, step, 46, 1.5);
    const [liquidRipple, liquidRippleVelocity] = settle(state.liquidRipple, state.liquidRippleVelocity, step, 68, 1.5);
    return {
        liquidTilt: clamp(liquidTilt, 16),
        liquidTiltVelocity,
        liquidRipple: clamp(liquidRipple, 8),
        liquidRippleVelocity
    };
}
export function liquidSurfaceDisplacement(state, x, centerX, halfWidth, waveTime) {
    const position = clamp((x - centerX) / halfWidth, 1);
    return state.liquidTilt * position
        + state.liquidRipple * Math.sin(position * Math.PI * 1.5 + waveTime * 3);
}
//# sourceMappingURL=liquidMotion.js.map