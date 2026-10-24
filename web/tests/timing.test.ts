import {describe,it,expect} from 'vitest';
import {planPhysicsSteps} from '../src/game/timing';
import {FIXED_DT} from '../src/physics/config';
describe('render-independent physical clock',()=>{
  it.each([30,60,120])('%i FPS schedules exactly 240 fixed steps per second',fps=>{
    let accumulator=0,steps=0;for(let frame=0;frame<fps;frame++){const p=planPhysicsSteps(accumulator,1/fps,true);expect(p.fault).toBeNull();steps+=p.steps;accumulator=p.remainder;}
    expect(steps).toBe(240);expect(accumulator).toBeLessThan(1e-10);
  });
  it('preserves substep remainder and drops backlog during pause',()=>{
    const first=planPhysicsSteps(0,FIXED_DT*.6,true);expect(first.steps).toBe(0);
    expect(planPhysicsSteps(first.remainder,FIXED_DT*.6,true).steps).toBe(1);
    expect(planPhysicsSteps(first.remainder,.1,false)).toEqual({steps:0,remainder:0,fault:null});
  });
  it('never simulates a long interruption, invalid clock, or excess catch-up',()=>{
    for(const dt of [.251,2,NaN,Infinity,-1]){const p=planPhysicsSteps(0,dt,true);expect(p.steps).toBe(0);expect(p.fault).not.toBeNull();}
    expect(planPhysicsSteps(0,.25,true).steps).toBe(60);
    expect(planPhysicsSteps(.1,.25,true).fault).not.toBeNull();
    expect(planPhysicsSteps(NaN,.01,true).fault).not.toBeNull();
  });
});
