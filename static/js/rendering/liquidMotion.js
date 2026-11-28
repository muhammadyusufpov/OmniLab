const profiles = {
    beaker: { drag: 2.4, pour: 24, ripple: 65, spring: 46, damping: 1.5, width: 86 },
    flask: { drag: 1.7, pour: 17, ripple: 48, spring: 38, damping: 1.8, width: 106 },
    tube: { drag: 0.8, pour: 7, ripple: 24, spring: 62, damping: 2.4, width: 33 },
    cylinder: { drag: 1, pour: 9, ripple: 30, spring: 58, damping: 2.2, width: 38 }
};
const clamp = (value, limit) => Math.max(-limit, Math.min(limit, value));
export function moveLiquid(state, dx, dy, vessel = 'beaker') {
    const profile = profiles[vessel];
    return {
        liquidTilt: state.liquidTilt,
        liquidTiltVelocity: clamp(state.liquidTiltVelocity - dx * profile.drag, 85),
        liquidRipple: state.liquidRipple,
        liquidRippleVelocity: clamp(state.liquidRippleVelocity + Math.hypot(dx, dy) * profile.drag * 0.58, 90)
    };
}
export function pourIntoLiquid(state, vessel = 'beaker') {
    const profile = profiles[vessel];
    return {
        liquidTilt: state.liquidTilt,
        liquidTiltVelocity: clamp(state.liquidTiltVelocity + profile.pour, 85),
        liquidRipple: state.liquidRipple,
        liquidRippleVelocity: clamp(state.liquidRippleVelocity + profile.ripple, 90)
    };
}
function settle(position, velocity, elapsed, spring, damping) {
    const nextVelocity = velocity + (-spring * position - damping * velocity) * elapsed;
    const nextPosition = position + nextVelocity * elapsed;
    return Math.abs(nextPosition) < 0.02 && Math.abs(nextVelocity) < 0.15
        ? [0, 0]
        : [nextPosition, nextVelocity];
}
export function settleLiquid(state, elapsed, vessel = 'beaker') {
    const step = Math.min(Math.max(elapsed, 0), 0.05);
    const profile = profiles[vessel];
    const [liquidTilt, liquidTiltVelocity] = settle(state.liquidTilt, state.liquidTiltVelocity, step, profile.spring, profile.damping);
    const [liquidRipple, liquidRippleVelocity] = settle(state.liquidRipple, state.liquidRippleVelocity, step, profile.spring * 1.48, profile.damping);
    return {
        liquidTilt: clamp(liquidTilt, 16),
        liquidTiltVelocity,
        liquidRipple: clamp(liquidRipple, 8),
        liquidRippleVelocity
    };
}
export function surfaceHalfWidth(vessel, liquidTopY, centerY) {
    if (vessel !== 'flask')
        return profiles[vessel].width;
    const slope = (liquidTopY - (centerY - 30)) / 130;
    return 23 + (106 - 23) * Math.max(0, Math.min(1, slope));
}
export function liquidSurfaceDisplacement(state, x, centerX, halfWidth, waveTime) {
    const position = clamp((x - centerX) / halfWidth, 1);
    return state.liquidTilt * position
        + state.liquidRipple * Math.sin(position * Math.PI * 1.5 + waveTime * 3);
}
//# sourceMappingURL=liquidMotion.js.map