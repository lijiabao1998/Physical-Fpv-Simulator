import { inverseRotate, rotate, type Q4, type V3 } from '../physics/math';

/** Rotation is body-to-world wxyz; local +x is the permitted crossing normal. */
export interface OrientedGate {
  center: V3;
  rotation: Q4;
  width: number;
  height: number;
  depth: number;
}

// These must agree with the Rapier drone collider and the four-sided gate bars.
const DRONE_HALF: V3 = [.14, .14, .06];
const FRAME_HALF = .10;
const CLEARANCE_EPSILON = 1e-9;
const CORNERS: V3[] = [-1, 1].flatMap(x => [-1, 1].flatMap(y =>
  [-1, 1].map(z => [x * DRONE_HALF[0], y * DRONE_HALF[1], z * DRONE_HALF[2]] as V3)));

function finiteVector(v: readonly number[], length: number) {
  return Array.isArray(v) && v.length === length && v.every(Number.isFinite);
}

function unit(q: Q4): Q4 | null {
  if (!finiteVector(q, 4)) return null;
  const n = Math.hypot(...q);
  return Number.isFinite(n) && n > 1e-12 ? q.map(value => value / n) as Q4 : null;
}

const conjugate = (q: Q4): Q4 => [q[0], -q[1], -q[2], -q[3]];
function multiply(a: Q4, b: Q4): Q4 {
  const [w, x, y, z] = a, [v, i, j, k] = b;
  return [w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
    w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v];
}

/** Exact support envelope of a cuboid along the shortest quaternion arc.
 * A rotated corner's projection is A cos(theta) + B sin(theta) + C. Check
 * its endpoints and every stationary point, not just sampled attitudes.
 */
function attitudeEnvelope(from: Q4, to: Q4) {
  if (from.reduce((sum, v, i) => sum + v * to[i], 0) < 0) {
    to = to.map(v => -v) as Q4;
  }
  const delta = multiply(to, conjugate(from));
  const sine = Math.hypot(delta[1], delta[2], delta[3]);
  const angle = 2 * Math.atan2(sine, Math.max(0, delta[0]));
  const corners = CORNERS.map(corner => rotate(from, corner));
  if (sine < 1e-12) {
    return (axis: number, _start: number, _end: number) =>
      Math.max(...corners.map(corner => Math.abs(corner[axis])));
  }
  const u: V3 = [delta[1] / sine, delta[2] / sine, delta[3] / sine];
  return (axis: number, start: number, end: number) => {
    const lo = angle * start, hi = angle * end;
    let support = 0;
    for (const v of corners) {
      const c = u[axis] * (u[0]*v[0] + u[1]*v[1] + u[2]*v[2]);
      const a = v[axis] - c;
      const b = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]][axis];
      const magnitude = (theta: number) => Math.abs(a*Math.cos(theta) + b*Math.sin(theta) + c);
      support = Math.max(support, magnitude(lo), magnitude(hi));
      const phase = Math.atan2(b, a);
      // Both extrema matter because support is an absolute projection.
      const first = Math.ceil((lo - phase) / Math.PI);
      const last = Math.floor((hi - phase) / Math.PI);
      for (let k = first; k <= last; k++) {
        support = Math.max(support, magnitude(phase + k * Math.PI));
      }
    }
    return support;
  };
}

/** Return the segment's forward plane-crossing fraction, or null.
 *
 * This is stateless geometry: course order and collision/run validity belong
 * to the caller. A negative-to-zero crossing belongs to this segment; starting
 * on the plane does not score again. Attitude follows the shortest quaternion
 * arc. Clearance conservatively covers the entire sampled interval in which
 * the cuboid can overlap the finite-depth frame, not only the centre hit.
 * Independent centre/support maxima can reject a marginal skim, but cannot
 * admit one. No motion beyond the supplied segment is predicted.
 */
export function intersectGate(
  gate: OrientedGate,
  previous: V3,
  current: V3,
  previousQ: Q4 = [1, 0, 0, 0],
  currentQ: Q4 = previousQ,
): number | null {
  if (!gate || !finiteVector(gate.center, 3) || !finiteVector(previous, 3) ||
    !finiteVector(current, 3) || ![gate.width, gate.height, gate.depth].every(Number.isFinite) ||
    gate.width <= 2*FRAME_HALF || gate.height <= 2*FRAME_HALF || gate.depth <= 0) return null;
  const gateQ = unit(gate.rotation), oldQ = unit(previousQ), newQ = unit(currentQ);
  if (!gateQ || !oldQ || !newQ) return null;
  const local = (p: V3) => {
    const point = inverseRotate(gateQ, p.map((v, i) => v - gate.center[i]) as V3);
    // Transform roundoff must not turn the same plane endpoint into a second
    // negative-to-positive crossing. This scales with input precision, not a
    // gameplay-sized proximity threshold, and still admits tiny real steps.
    const roundoff = 16 * Number.EPSILON * Math.max(1, ...p.map(Math.abs), ...gate.center.map(Math.abs));
    if (Math.abs(point[0]) <= roundoff) point[0] = 0;
    return point;
  };
  const a = local(previous), b = local(current);
  if (!finiteVector(a, 3) || !finiteVector(b, 3) || !(a[0] < 0 && b[0] >= 0)) return null;
  const travel = b.map((v, i) => v - a[i]) as V3;
  if (!finiteVector(travel, 3) || travel[0] <= 0) return null;
  const alpha = -a[0] / travel[0];
  if (!Number.isFinite(alpha) || alpha <= 0 || alpha > 1) return null;

  const intoGate = conjugate(gateQ);
  const support = attitudeEnvelope(multiply(intoGate, oldQ), multiply(intoGate, newQ));
  // Bound normal support over the full attitude arc before restricting the
  // aperture check to the potential frame-contact interval.
  const slab = gate.depth / 2 + support(0, 0, 1);
  const start = Math.max(0, (-slab - a[0]) / travel[0]);
  const end = Math.min(1, (slab - a[0]) / travel[0]);
  if (![slab, start, end].every(Number.isFinite) || start > end) return null;
  for (const axis of [1, 2]) {
    const centerExtent = Math.max(Math.abs(a[axis] + start*travel[axis]), Math.abs(a[axis] + end*travel[axis]));
    const aperture = (axis === 1 ? gate.width : gate.height) / 2 - FRAME_HALF;
    const extent = centerExtent + support(axis, start, end);
    // Contact with a bar is not a legal passage; fail closed on roundoff.
    if (!Number.isFinite(extent) || extent >= aperture - CLEARANCE_EPSILON) return null;
  }
  return alpha;
}
