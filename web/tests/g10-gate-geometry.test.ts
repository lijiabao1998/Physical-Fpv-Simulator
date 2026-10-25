import { describe, expect, it } from 'vitest';
import { intersectGate, type OrientedGate } from '../src/game/gate-geometry';
import { add, normalized, rotate, type Q4, type V3 } from '../src/physics/math';

const ID: Q4 = [1, 0, 0, 0];
const base: OrientedGate = { center: [0, 0, 0], rotation: ID, width: 2, height: 2, depth: .22 };
const axisQ = (axis: 0 | 1 | 2, angle: number): Q4 => {
  const q: Q4 = [Math.cos(angle/2), 0, 0, 0]; q[axis+1] = Math.sin(angle/2); return q;
};
const multiply = (a: Q4, b: Q4): Q4 => [
  a[0]*b[0]-a[1]*b[1]-a[2]*b[2]-a[3]*b[3],
  a[0]*b[1]+a[1]*b[0]+a[2]*b[3]-a[3]*b[2],
  a[0]*b[2]-a[1]*b[3]+a[2]*b[0]+a[3]*b[1],
  a[0]*b[3]+a[1]*b[2]-a[2]*b[1]+a[3]*b[0],
];
const world = (g: OrientedGate, p: V3): V3 => add(g.center, rotate(normalized(g.rotation), p));
const straight = (g = base, y = 0, z = 0, q = ID) => intersectGate(g, [-1,y,z], [1,y,z], q);

describe('G10 independent three-dimensional gate geometry', () => {
  it('returns the actual continuous plane fraction, including a fast traversal', () => {
    expect(straight()).toBe(.5);
    expect(intersectGate(base, [-3,0,0], [1,0,0])).toBe(.75);
    expect(intersectGate(base, [-10000,0,0], [10000,0,0])).toBe(.5);
    expect(intersectGate(base, [-1,0,0], [0,0,0])).toBe(1);
  });

  it('rejects reverse, same-side, proximity-only, stationary and tangent motion', () => {
    for (const [a,b] of [
      [[1,0,0],[-1,0,0]], [[-1,0,0],[-.001,0,0]], [[.001,0,0],[1,0,0]],
      [[0,0,0],[1,0,0]], [[0,-.5,0],[0,.5,0]], [[0,0,0],[0,0,0]],
      [[-1,0,0],[-1,.5,.2]],
    ] as [V3,V3][]) expect(intersectGate(base,a,b)).toBeNull();
  });

  it('accepts a legal oblique trajectory and rejects both horizontal and vertical misses', () => {
    expect(intersectGate(base, [-1,-.2,-.1], [1,.2,.1])).toBe(.5);
    for (const [y,z] of [[2,0],[-2,0],[0,2],[0,-2],[.8,.8]]) expect(straight(base,y,z)).toBeNull();
  });

  it('uses exact cuboid extents and bar thickness on all four aperture edges', () => {
    for (const sign of [-1,1]) {
      expect(straight(base,sign*.76,0)).toBeNull();
      expect(straight(base,sign*.75999,0)).toBe(.5);
      expect(straight(base,0,sign*.84)).toBeNull();
      expect(straight(base,0,sign*.83999)).toBe(.5);
    }
    expect(straight(base,.83,0)).toBeNull(); // Centre fits, body does not.
    expect(straight({...base,width:.4})).toBeNull();
    expect(straight({...base,height:.3})).toBeNull();
    expect(straight({...base,width:.6,height:.4})).toBe(.5);
  });

  it('projects collider orientation instead of using a spherical or point aircraft', () => {
    const roll = axisQ(0,Math.PI/2), yaw = axisQ(2,Math.PI/4);
    expect(straight(base,0,.80)).toBe(.5);
    expect(straight(base,0,.80,roll)).toBeNull();
    expect(straight(base,.80,0)).toBeNull();
    expect(straight(base,.80,0,roll)).toBe(.5);
    expect(straight(base,.72,0)).toBe(.5);
    expect(straight(base,.72,0,yaw)).toBeNull();
  });

  it('checks intermediate attitude extrema, not just either endpoint orientation', () => {
    const g = {...base,width:.57}, quarterTurn = axisQ(2,Math.PI/2);
    expect(straight(g,0,0,ID)).toBe(.5);
    expect(straight(g,0,0,quarterTurn)).toBe(.5);
    expect(intersectGate(g,[-1,0,0],[1,0,0],ID,quarterTurn)).toBeNull();
    expect(intersectGate({...g,width:.60},[-1,0,0],[1,0,0],ID,quarterTurn)).toBe(.5);
  });

  it('uses the shortest attitude arc and treats quaternion signs equivalently', () => {
    const a = axisQ(2,170*Math.PI/180), b = axisQ(2,-170*Math.PI/180);
    const g = {...base,width:.54};
    expect(intersectGate(g,[-1,0,0],[1,0,0],a,b)).toBe(.5);
    expect(intersectGate(g,[-1,0,0],[1,0,0],a,b.map(v=>-v) as Q4)).toBe(.5);
    const q = axisQ(2,.7);
    expect(intersectGate(base,[-1,0,0],[1,0,0],q,q.map(v=>-v) as Q4)).toBe(.5);
  });

  it('uses local normal for yawed gates with no world-x motion', () => {
    const g = {...base,center:[10,20,3] as V3,rotation:axisQ(2,Math.PI/2)};
    expect(intersectGate(g,[10,19,3],[10,21,3],g.rotation)).toBeCloseTo(.5,13);
    expect(intersectGate(g,[10,21,3],[10,19,3],g.rotation)).toBeNull();
    expect(intersectGate(g,[9,21,3],[11,21,3],g.rotation)).toBeNull();
  });

  it('respects pitch, yaw and roll together for plane, aperture and body attitude', () => {
    const rotation = multiply(axisQ(2,1.1),multiply(axisQ(1,.7),axisQ(0,.3)));
    const g = {...base,center:[12,-8,5] as V3,rotation};
    const a: V3 = [-3,.15,-.1], b: V3 = [1,.15,-.1];
    expect(intersectGate(g,world(g,a),world(g,b),rotation)).toBeCloseTo(.75,13);
    expect(intersectGate(g,world(g,b),world(g,a),rotation)).toBeNull();
    expect(intersectGate(g,world(g,[-1,1,0]),world(g,[1,1,0]),rotation)).toBeNull();
    expect(intersectGate(g,world(g,[-1,0,1]),world(g,[1,0,1]),rotation)).toBeNull();
    const roll = multiply(rotation,axisQ(0,Math.PI/2));
    expect(intersectGate(g,world(g,[-1,0,.8]),world(g,[1,0,.8]),roll)).toBeNull();
  });

  it('remains invariant under arbitrary rigid transforms', () => {
    for (let i=0;i<48;i++) {
      const rotation = multiply(axisQ(2,i*.31),multiply(axisQ(1,i*.19),axisQ(0,i*.11)));
      const g = {...base,center:[i*3-40,Math.sin(i)*20,5+i] as V3,rotation};
      const q = multiply(rotation,axisQ(0,.4));
      expect(intersectGate(g,world(g,[-1,.2,.1]),world(g,[3,.2,.1]),q)).toBeCloseTo(.25,12);
      expect(intersectGate(g,world(g,[-1,.9,0]),world(g,[3,.9,0]),q)).toBeNull();
      const onPlane = world(g,[0,.2,.1]);
      expect(intersectGate(g,world(g,[-1,.2,.1]),onPlane,q)).toBeCloseTo(1,12);
      expect(intersectGate(g,onPlane,world(g,[1,.2,.1]),q)).toBeNull();
    }
  });

  it('checks the finite-depth slab rather than only the centre-plane intersection', () => {
    const a: V3 = [-2,-1.5,0], b: V3 = [2,1.5,0];
    expect(intersectGate({...base,depth:.02},a,b)).toBe(.5);
    expect(intersectGate({...base,depth:2},a,b)).toBeNull();
    // Endpoint misses outside the frame-contact interval do not reject a safe passage.
    expect(intersectGate(base,[-20,-4,0],[20,4,0])).toBe(.5);
  });

  it('does not confuse a later gate crossing with the missed earlier gate', () => {
    const first = {...base,center:[10,0,0] as V3}, later = {...base,center:[20,0,0] as V3};
    expect(intersectGate(first,[19,0,0],[21,0,0])).toBeNull();
    expect(intersectGate(later,[19,0,0],[21,0,0])).toBe(.5);
    // The geometry helper reports independently; ordered course state must reject skipping.
    expect(intersectGate(first,[9,0,0],[21,0,0])).toBeCloseTo(1/12,14);
    expect(intersectGate(later,[9,0,0],[21,0,0])).toBeCloseTo(11/12,14);
  });

  it('fails closed on nonfinite or degenerate geometry and attitude', () => {
    for (const field of ['width','height','depth'] as const) {
      for (const value of [NaN,Infinity,-Infinity,0,-1]) expect(straight({...base,[field]:value})).toBeNull();
    }
    expect(straight({...base,width:.2})).toBeNull();
    expect(straight({...base,height:.2})).toBeNull();
    for (const q of [[0,0,0,0],[NaN,0,0,0],[1,Infinity,0,0]] as Q4[]) {
      expect(straight({...base,rotation:q})).toBeNull();
      expect(straight(base,0,0,q)).toBeNull();
      expect(intersectGate(base,[-1,0,0],[1,0,0],ID,q)).toBeNull();
    }
    for (let axis=0;axis<3;axis++) {
      const bad: V3 = [0,0,0]; bad[axis]=NaN;
      expect(intersectGate(base,bad,[1,0,0])).toBeNull();
      expect(intersectGate(base,[-1,0,0],bad)).toBeNull();
      expect(straight({...base,center:bad})).toBeNull();
    }
    expect(intersectGate(base,[-1e308,0,0],[1e308,0,0])).toBeNull();
  });

  it('normalizes finite scaled quaternions without mutating any inputs', () => {
    const g = {...base,rotation:[2,0,0,0] as Q4};
    const a: V3 = [-1,0,0], b: V3 = [1,0,0], q: Q4 = [3,0,0,0];
    const before = JSON.stringify([g,a,b,q]);
    expect(intersectGate(g,a,b,q)).toBe(.5);
    expect(JSON.stringify([g,a,b,q])).toBe(before);
  });

  it('keeps alpha stable for short steps and shared-plane endpoints without duplicate scoring', () => {
    expect(intersectGate(base,[-1e-10,0,0],[3e-10,0,0])).toBeCloseTo(.25,15);
    expect(intersectGate(base,[-1,0,0],[0,0,0])).toBe(1);
    expect(intersectGate(base,[0,0,0],[1,0,0])).toBeNull();
  });
});

// Independent dense SLERP/body-axis reference checks the analytic swept support.
function slerp(a: Q4, b: Q4, t: number): Q4 {
  let cosine = a.reduce((sum,v,i)=>sum+v*b[i],0);
  if (cosine < 0) { b=b.map(v=>-v) as Q4; cosine=-cosine; }
  if (cosine > .9995) return normalized(a.map((v,i)=>v+t*(b[i]-v)) as Q4);
  const angle = Math.acos(Math.min(1,cosine)), denominator = Math.sin(angle);
  return a.map((v,i)=>(v*Math.sin((1-t)*angle)+b[i]*Math.sin(t*angle))/denominator) as Q4;
}

it('G10 analytic orientation envelope agrees conservatively with independent dense SLERP projections', () => {
  const bodyAxes: V3[] = [[1,0,0],[0,1,0],[0,0,1]], half = [.14,.14,.06];
  for (let i=0;i<24;i++) {
    const a = normalized(multiply(axisQ(0,.3+i*.47),axisQ(2,.7+i*.13)));
    const b = normalized(multiply(axisQ(1,1.7+i*.17),axisQ(2,-.8-i*.29)));
    const maxima = [0,0,0];
    for (let step=0;step<=400;step++) {
      const q = slerp(a,b,step/400), axes = bodyAxes.map(axis=>rotate(q,axis));
      for (const axis of [1,2]) maxima[axis] = Math.max(maxima[axis],axes.reduce((sum,v,j)=>sum+half[j]*Math.abs(v[axis]),0));
    }
    for (const axis of [1,2]) {
      const field = axis===1?'width':'height';
      const tight = {...base,width:10,height:10,[field]:2*(.1+maxima[axis]-1e-6)};
      const clear = {...tight,[field]:2*(.1+maxima[axis]+.002)};
      expect(intersectGate(tight,[-.05,0,0],[.05,0,0],a,b)).toBeNull();
      expect(intersectGate(clear,[-.05,0,0],[.05,0,0],a,b)).toBe(.5);
    }
  }
});
