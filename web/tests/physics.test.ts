import {beforeAll,describe,expect,it} from 'vitest';
import {Powertrain} from '../src/physics/powertrain';
import {FlightWorld,initPhysics} from '../src/physics/world';
import {DEFAULT_MODEL,GRAVITY,assemblyModel,DEFAULT_ASSEMBLY} from '../src/physics/config';
import {motorDuties,ZERO} from '../src/physics/controller';
import {euler,norm} from '../src/physics/math';
import type {V3,Q4} from '../src/physics/math';
import fixtures from './reference-fixtures';

beforeAll(async()=>{await initPhysics();});
const zero={thrust:[0,0,0,0],torque:[0,0,0,0]};
describe('A: analytical physics and bounded models',()=>{
  it('matches the pinned synthetic circuit example and passive power closure',()=>{
    const p=new Powertrain(),o=p.evaluate([.6,.6,.6,.6]);
    expect(o.voltage).toBeCloseTo(15.2041045435,9);expect(o.current).toBeCloseTo(24.0811553437,9);
    expect(o.thrust[0]).toBeCloseTo(3.12363726,7);expect(Math.abs(o.powerError)).toBeLessThan(1e-8);
    expect(Math.abs(o.residual)).toBeLessThan(1e-11);
    expect(p.evaluate([1,1,1,1]).voltage).toBeLessThan(o.voltage);
  });
  it('closes charge, state energy, all electrical losses and cell heat under varying load',()=>{
    const p=new Powertrain();
    for(let i=0;i<2400;i++)p.step([.3+(i%100)/200,.45,.65,.4],1/240,4);
    const a=p.audit();
    expect(Math.abs(a.energyError)).toBeLessThan(1e-6);expect(Math.abs(a.sourceError)).toBeLessThan(1e-6);
    expect(Math.abs(a.chargeError)).toBeLessThan(1e-7);expect(Math.abs(a.thermalError)).toBeLessThan(1e-7);
    expect(p.soc).toBeLessThan(.9);expect(p.temperature).toBeGreaterThan(298.15);
  });
  it('zero duty produces zero thrust, current and power; no free control lift',()=>{
    const p=new Powertrain(),o=p.step([0,0,0,0],1/240);
    expect(o.thrust).toEqual([0,0,0,0]);expect(o.current).toBe(0);expect(p.soc).toBe(.9);
    expect(motorDuties([1,0,0,0],[0,0,0],{...ZERO,roll:1},'angle')).toEqual([0,0,0,0]);
  });
  it('freefall follows gravity and total energy converges without thrust',()=>{
    const w=new FlightWorld(DEFAULT_MODEL,false); w.setInitial([0,0,20]);
    for(let i=0;i<240;i++) w.step(zero,1/240,false);
    // Rapier uses Float32; 240 repeated velocity increments accumulate roundoff.
    expect(Math.abs(w.velocity[2]+GRAVITY)).toBeLessThan(2e-4);
    expect(Math.abs(w.position[2]-(20-.5*GRAVITY))).toBeLessThan(.025);
    const energy=w.kinetic()+DEFAULT_MODEL.mass*GRAVITY*w.position[2];
    expect(Math.abs(energy-DEFAULT_MODEL.mass*GRAVITY*20)).toBeLessThan(.2); w.dispose();
  });
  it('horizontal static hover balances weight, insufficient thrust descends',()=>{
    for(const factor of [1,.5]) {
      const w=new FlightWorld(DEFAULT_MODEL,false);w.setInitial([0,0,20]);
      for(let i=0;i<240;i++)w.step({thrust:Array(4).fill(DEFAULT_MODEL.mass*GRAVITY/4*factor),torque:[0,0,0,0]},1/240,false);
      if(factor===1) expect(Math.abs(w.position[2]-20)).toBeLessThan(1e-4);
      else expect(w.velocity[2]).toBeCloseTo(-GRAVITY*.5,4);
      w.dispose();
    }
  });
  it.each([[0,1],[1,-1]] as const)('rotor 1 gives correct lever moment axis %s', (axis,sign)=>{
    const w=new FlightWorld(DEFAULT_MODEL,false);w.setInitial([0,0,20]);
    w.step({thrust:[1,0,0,0],torque:[0,0,0,0]},1/240,false);
    expect(w.rates[axis]*sign).toBeGreaterThan(0);w.dispose();
  });
  it('alternating rotor drag moments have opposite yaw signs and normalize quaternion',()=>{
    for(const rotor of [0,1]) {
      const w=new FlightWorld(DEFAULT_MODEL,false);w.setInitial([0,0,20]);
      const t=[0,0,0,0];t[rotor]=.01;
      for(let i=0;i<100;i++)w.step({thrust:[0,0,0,0],torque:t},1/240,false);
      expect(w.rates[2]*(rotor===0?1:-1)).toBeGreaterThan(0);
      expect(Math.hypot(...w.quaternion)).toBeCloseTo(1,10);w.dispose();
    }
  });
  it('unpowered ground and wall contact do not inject kinetic energy',()=>{
    for(const [position,velocity] of [[[0,0,.3],[1,0,-3]],[[9,2.1,2],[5,0,0]]] as [V3,V3][]) {
      const w=new FlightWorld(DEFAULT_MODEL,true);w.world.gravity={x:0,y:0,z:0};w.setInitial(position,velocity);
      const initial=w.kinetic();let peak=initial;
      for(let i=0;i<180;i++){w.step(zero,1/240,false);peak=Math.max(peak,w.kinetic());}
      expect(w.contacts).toBeGreaterThan(0);expect(peak).toBeLessThanOrEqual(initial+1e-4);
      expect(w.kinetic()).toBeLessThan(initial);w.dispose();
    }
  });
  it('rejects nonfinite/out of range input before power state mutation',()=>{
    const p=new Powertrain();const before=JSON.stringify(p);
    for(const d of [[NaN,0,0,0],[2,0,0,0],[-1,0,0,0],[1],[Infinity,0,0,0]])expect(()=>p.step(d,1/240)).toThrow();
    for(const dt of [0,-1,.5,NaN])expect(()=>p.step([.5,.5,.5,.5],dt)).toThrow();
    expect(JSON.stringify(p)).toBe(before);
    expect(()=>assemblyModel({...DEFAULT_ASSEMBLY,frame:'bad'} as never)).toThrow();
  });
  it('assembly genuinely changes weight, equilibrium duty, current and prop thrust',()=>{
    const heavy=assemblyModel({...DEFAULT_ASSEMBLY,battery:'endurance'});
    const small=assemblyModel({...DEFAULT_ASSEMBLY,propeller:'4inch'});
    const motor=assemblyModel({...DEFAULT_ASSEMBLY,motor:'torque'});
    const p=new Powertrain();expect(new Powertrain(heavy).hover()).toBeGreaterThan(p.hover());
    expect(new Powertrain(small).evaluate([.6,.6,.6,.6]).thrust[0]).toBeLessThan(p.evaluate([.6,.6,.6,.6]).thrust[0]);
    expect(new Powertrain(motor).evaluate([.6,.6,.6,.6]).current).not.toBeCloseTo(p.evaluate([.6,.6,.6,.6]).current,2);
  });
  it('Angle commands restore bank; Acro neutral damps rate without horizon leveling',()=>{
    for(const mode of ['angle','acro'] as const) {
      const w=new FlightWorld(DEFAULT_MODEL,false),p=new Powertrain();w.setInitial([0,0,20],[0,0,0],[Math.cos(.2),Math.sin(.2),0,0]);
      for(let i=0;i<360;i++){const d=motorDuties(w.quaternion,w.rates,{...ZERO,throttle:p.hover()},mode);w.step(p.step(d,1/240),1/240);}
      const bank=Math.abs(euler(w.quaternion)[0]);
      if(mode==='angle')expect(bank).toBeLessThan(.03);else expect(bank).toBeGreaterThan(.3);
      w.dispose();
    }
  });
});

describe('B: browser equations vs pinned Python trajectories',()=>{
  for(const f of fixtures.cases)it(f.name,()=>{
    const w=new FlightWorld(DEFAULT_MODEL,false),p=new Powertrain();w.setInitial([0,0,20],f.initialVelocity as V3);
    let n=0;
    for(let i=0;i<Math.round(f.duration/f.dt);i++) {
      const load=f.duties?p.step(f.duties,f.dt,norm(w.velocity)):p.evaluate([0,0,0,0]);
      w.step(f.directThrust?{thrust:f.directThrust,torque:[0,0,0,0]}:load,f.dt);
      if((i+1)%12===0) {
        const ref=f.trace[n++];
        expect(norm(w.position.map((x,j)=>x-ref.position[j]) as V3)).toBeLessThan(.03);
        expect(norm(w.velocity.map((x,j)=>x-ref.velocity[j]) as V3)).toBeLessThan(.02);
        const angle=2*Math.acos(Math.min(1,Math.abs(w.quaternion.reduce((s,x,j)=>s+x*ref.q[j],0))));
        expect(angle).toBeLessThan(.012);expect(Math.abs(load.voltage-ref.voltage)).toBeLessThan(2e-9);
        if(f.duties)for(let j=0;j<4;j++)expect(Math.abs(load.thrust[j]-ref.thrust[j])).toBeLessThan(2e-9);
        expect(Math.abs(p.soc-ref.soc)).toBeLessThan(2e-12);
      }
    }
    w.dispose();
  });
  it('freefall position error decreases with timestep 120 -> 240 -> 480 Hz',()=>{
    const errors=[120,240,480].map(hz=>{
      const w=new FlightWorld(DEFAULT_MODEL,false);w.setInitial([0,0,20]);
      for(let i=0;i<hz;i++)w.step(zero,1/hz,false);
      const err=Math.abs(w.position[2]-(20-GRAVITY/2));w.dispose();return err;
    });
    expect(errors[1]).toBeLessThan(errors[0]*.7);expect(errors[2]).toBeLessThan(errors[1]*.7);
  });
  it('controller roll, pitch and yaw targets produce their intended body-rate directions',()=>{
    for(const [key,axis] of [['roll',0],['pitch',1],['yaw',2]] as const) {
      const w=new FlightWorld(DEFAULT_MODEL,false),p=new Powertrain();w.setInitial([0,0,20]);
      for(let i=0;i<60;i++)w.step(p.step(motorDuties(w.quaternion,w.rates,{...ZERO,throttle:.5,[key]:.3},'acro'),1/240),1/240);
      expect(w.rates[axis]).toBeGreaterThan(.1);w.dispose();
    }
  });
  it('float quaternions have no sign-sensitive comparison assumption',()=>{
    const q: Q4=[-1,0,0,0];expect(euler(q)).toEqual([0,-0,0]);
  });
});

describe('independent rigid-body audit',()=>{
  it('torque-free anisotropic body follows Euler gyroscopic coupling',()=>{
    const w=new FlightWorld(DEFAULT_MODEL,false);w.world.gravity={x:0,y:0,z:0};
    w.setInitial([0,0,20],[0,0,0],[1,0,0,0],[1,2,3]);
    const dt=1e-4;
    w.step(zero,dt,false);
    // I=(.005,.005,.009): dωx=-.8 ωy ωz, dωy=.8 ωz ωx, dωz=0.
    expect(Math.abs((w.rates[0]-1)/dt-(-4.8))).toBeLessThan(.03);
    expect(Math.abs((w.rates[1]-2)/dt-2.4)).toBeLessThan(.03);
    expect(Math.abs((w.rates[2]-3)/dt)).toBeLessThan(.03);
    w.dispose();
  });
  it('invalid rotor forces cannot mutate the rigid-body state',()=>{
    const w=new FlightWorld(DEFAULT_MODEL,false);w.setInitial([0,0,20]);const p=w.position;
    for(const thrust of [[NaN,0,0,0],[101,0,0,0],[-1,0,0,0],[1]])expect(()=>w.step({thrust,torque:[0,0,0,0]},1/240)).toThrow();
    expect(w.position).toEqual(p);expect(w.velocity).toEqual([0,0,0]);w.dispose();
  });
});
