import { finiteRange, type V3 } from './math';
export const GRAVITY = 9.80665;
export const RHO = 1.225;
export const FIXED_DT = 1/240;
export const INITIAL_SOC = 0.9;
/** Every dimensional value here is a synthetic fixture, not a hardware rating. */
export interface Assembly {
  frame: 'trainer' | 'light';
  battery: 'standard' | 'endurance';
  motor: 'balanced' | 'torque';
  propeller: '5inch' | '4inch';
}
export const DEFAULT_ASSEMBLY: Assembly = {frame:'trainer',battery:'standard',motor:'balanced',propeller:'5inch'};
export function assemblyModel(a: Assembly) {
  if (!['trainer','light'].includes(a.frame) || !['standard','endurance'].includes(a.battery) || !['balanced','torque'].includes(a.motor) || !['5inch','4inch'].includes(a.propeller)) throw Error('Unknown assembly part');
  const frameMass = a.frame==='trainer'?0.248:0.188;
  const batteryMass = a.battery==='standard'?0.28:0.39;
  const motorMass = a.motor==='balanced'?0.028:0.033;
  const propMass = a.propeller==='5inch'?0.005:0.004;
  const fixedMass = 0.06;
  const mass = frameMass+batteryMass+4*(motorMass+propMass)+fixedMass;
  const arm = 0.12;
  const inertia: V3 = [0.005,0.005,0.009].map(x=>x*mass/0.72) as V3;
  return {mass,arm,inertia,frameMass,batteryMass,motorMass,propMass,fixedMass,
    capacityAh:a.battery==='standard'?3:4.5,
    motorK:a.motor==='balanced'?0.0045:0.0052,
    diameter:a.propeller==='5inch'?0.127:0.1016,
    mounts: [[1,1],[-1,1],[-1,-1],[1,-1]].map(([x,y])=>[x*arm/Math.sqrt(2),y*arm/Math.sqrt(2),0] as V3),
  };
}
export type Model = ReturnType<typeof assemblyModel>;
export const DEFAULT_MODEL = assemblyModel(DEFAULT_ASSEMBLY);
export function validateDt(dt: number) { finiteRange(dt,1e-6,0.02,'dt'); }
