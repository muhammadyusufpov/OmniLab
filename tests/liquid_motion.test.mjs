import assert from 'node:assert/strict';
import test from 'node:test';

const { moveLiquid, settleLiquid, liquidSurfaceDisplacement } = await import(
    '../static/js/rendering/liquidMotion.js'
);

const still = {
    liquidTilt: 0,
    liquidTiltVelocity: 0,
    liquidRipple: 0,
    liquidRippleVelocity: 0
};

test('moving a filled vessel kicks the liquid surface in the opposite direction', () => {
    const kicked = moveLiquid(still, 20, 0);
    const moving = settleLiquid(kicked, 1 / 60);
    assert.ok(moving.liquidTilt < 0);
    assert.notEqual(liquidSurfaceDisplacement(moving, -50, 0, 50, 0),
        liquidSurfaceDisplacement(moving, 50, 0, 50, 0));
});

test('vertical movement creates a ripple that settles after the vessel stops', () => {
    let motion = moveLiquid(still, 0, 20);
    motion = settleLiquid(motion, 1 / 60);
    assert.ok(motion.liquidRipple > 0);
    for (let frame = 0; frame < 600; frame++) {
        motion = settleLiquid(motion, 1 / 60);
    }
    assert.deepEqual(motion, still);
});
