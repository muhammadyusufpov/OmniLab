import assert from 'node:assert/strict';
import test from 'node:test';

const { moveLiquid, pourIntoLiquid, settleLiquid, liquidSurfaceDisplacement, surfaceHalfWidth } = await import(
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

test('the same drag and pour produce vessel-sized motion', () => {
    const drag = ['beaker', 'flask', 'tube'].map(vessel =>
        Math.abs(moveLiquid(still, 10, 0, vessel).liquidTiltVelocity));
    const pour = ['beaker', 'flask', 'tube'].map(vessel =>
        pourIntoLiquid(still, vessel).liquidRippleVelocity);
    assert.ok(drag[0] > drag[1] && drag[1] > drag[2]);
    assert.ok(pour[0] > pour[1] && pour[1] > pour[2]);
});

test('flask surface narrows toward its neck', () => {
    assert.equal(surfaceHalfWidth('flask', -30, 0), 23);
    assert.equal(surfaceHalfWidth('flask', 100, 0), 106);
    assert.equal(surfaceHalfWidth('tube', 100, 0), 33);
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

test('a moved vessel keeps a visible ripple after two seconds, then settles', () => {
    let motion = moveLiquid(still, 0, 20);
    for (let frame = 0; frame < 120; frame++) motion = settleLiquid(motion, 1 / 60);
    assert.ok(Math.abs(motion.liquidRipple) > 0.25);
    for (let frame = 0; frame < 600; frame++) motion = settleLiquid(motion, 1 / 60);
    assert.deepEqual(motion, still);
});

test('pouring into existing liquid starts movement that outlasts the stream', () => {
    let motion = pourIntoLiquid(still);
    for (let frame = 0; frame < 15; frame++) motion = settleLiquid(motion, 1 / 60);
    assert.ok(Math.abs(motion.liquidRipple) > 1);
    assert.ok(Math.abs(motion.liquidTilt) > 0.1);
});
