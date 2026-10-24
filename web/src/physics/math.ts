export type V3 = [number, number, number];
/** Body -> world, wxyz. Right-handed x forward, y left, z up. */
export type Q4 = [number, number, number, number];
export const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
export const add = (a: V3, b: V3): V3 => [a[0]+b[0], a[1]+b[1], a[2]+b[2]];
export const scale = (a: V3, k: number): V3 => [a[0]*k, a[1]*k, a[2]*k];
export const dot = (a: V3, b: V3) => a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
export const norm = (a: V3) => Math.hypot(...a);
export const cross = (a: V3, b: V3): V3 => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
export function normalized(q: Q4): Q4 {
  const n = Math.hypot(...q);
  if (!Number.isFinite(n) || n < 1e-12) throw Error('Invalid quaternion');
  return q.map(x => x/n) as Q4;
}
export function rotate(q: Q4, v: V3): V3 {
  const [w,x,y,z] = q;
  const uv = cross([x,y,z],v), uuv = cross([x,y,z],uv);
  return add(v,add(scale(uv,2*w),scale(uuv,2)));
}
export const inverseRotate = (q: Q4,v: V3) => rotate([q[0],-q[1],-q[2],-q[3]],v);
export function euler(q: Q4): V3 {
  const [w,x,y,z]=q;
  return [Math.atan2(2*(w*x+y*z),1-2*(x*x+y*y)), Math.asin(clamp(2*(w*y-z*x),-1,1)), Math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))];
}
export function finiteRange(value: number, low: number, high: number, label: string) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high) throw Error(`${label} outside [${low}, ${high}]`);
  return value;
}
