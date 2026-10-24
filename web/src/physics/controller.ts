import { clamp, euler, finiteRange, type Q4, type V3 } from './math';
export type FlightMode = 'angle' | 'acro';
export interface Controls { throttle: number; roll: number; pitch: number; yaw: number }
export const ZERO: Controls = {throttle:0,roll:0,pitch:0,yaw:0};
export function validateControls(c: Controls) {
  finiteRange(c.throttle,0,1,'throttle');
  for(const k of ['roll','pitch','yaw'] as const) finiteRange(c[k],-1,1,k);
}
export function motorDuties(q: Q4, bodyRates: V3,c: Controls,mode: FlightMode, rate=3.5, angleLimit=.6): number[] {
  validateControls(c); finiteRange(rate,1,10,'rate');
  if(mode!=='angle'&&mode!=='acro') throw Error('Invalid flight mode');
  if(c.throttle<.015) return [0,0,0,0]; // no attitude-control thrust at zero throttle
  const angles=euler(q);
  const targets: V3 = mode==='angle'
    ? [clamp((c.roll*angleLimit-angles[0])*6,-rate,rate),clamp((c.pitch*angleLimit-angles[1])*6,-rate,rate),c.yaw*rate*.65]
    : [c.roll*rate,c.pitch*rate,c.yaw*rate*.65];
  const correction=targets.map((r,i)=>clamp((r-bodyRates[i])*(i===2?.025:.05),-.23,.23));
  return [[1,-1,1],[1,1,-1],[-1,1,1],[-1,-1,-1]].map(row=>clamp(c.throttle+row.reduce((s,x,i)=>s+x*correction[i],0),0,1));
}
