/** Reproducible numerical evidence, not a hardware or browser-rendering test. */
import {beforeAll,it,expect} from 'vitest';
import {mkdirSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {FlightWorld,initPhysics} from '../src/physics/world';
import {Powertrain} from '../src/physics/powertrain';
import {DEFAULT_MODEL,GRAVITY} from '../src/physics/config';
import {norm,type V3} from '../src/physics/math';
import fixtures from '../../reference/fixtures.json';

beforeAll(initPhysics);
const zero={thrust:[0,0,0,0],torque:[0,0,0,0]};
const vectorError=(a:readonly number[],b:readonly number[])=>Math.hypot(...a.map((v,i)=>v-b[i]));
const limits={positionM:.03,velocityMps:.02,attitudeRad:.012,voltageV:2e-9,thrustN:2e-9,soc:2e-12};
const rms=(a:number[])=>Math.sqrt(a.reduce((s,x)=>s+x*x,0)/a.length);

it('writes numerical comparison, refinement and passive-energy evidence with explicit gates',()=>{
  const trajectories=fixtures.cases.map(f=>{
    const refinements=[120,240,480].map(hz=>{
      const w=new FlightWorld(DEFAULT_MODEL,false),p=new Powertrain();
      w.setInitial([0,0,20],f.initialVelocity as V3);
      const samples:Record<string,number>[]=[];
      for(let i=0;i<Math.round(f.duration*hz);i++){
        const load=f.duties?p.step(f.duties,1/hz,norm(w.velocity)):p.evaluate([0,0,0,0]);
        const applied=f.directThrust?{thrust:f.directThrust,torque:[0,0,0,0]}:load;
        w.step(applied,1/hz);
        if((i+1)%(hz/20)===0){
          const r=f.trace[samples.length];
          const alignment=Math.min(1,Math.abs(w.quaternion.reduce((s,x,j)=>s+x*r.q[j],0)));
          samples.push({time:(i+1)/hz,positionM:vectorError(w.position,r.position),velocityMps:vectorError(w.velocity,r.velocity),
            attitudeRad:2*Math.acos(alignment),bodyRateRadps:vectorError(w.rates,r.rates),voltageV:Math.abs(load.voltage-r.voltage),
            thrustN:Math.max(...applied.thrust.map((x,j)=>Math.abs(x-r.thrust[j]))),soc:Math.abs(p.soc-r.soc)});
        }
      }
      w.dispose();
      const keys=Object.keys(samples[0]).filter(k=>k!=='time');
      return {hz,max:Object.fromEntries(keys.map(k=>[k,Math.max(...samples.map(s=>s[k]))])),
        rms:Object.fromEntries(keys.map(k=>[k,rms(samples.map(s=>s[k]))])),samples};
    });
    for(const [key,limit] of Object.entries(limits))expect(refinements[1].max[key],`${f.name}: ${key}`).toBeLessThan(limit);
    // Same 0.7 refinement criterion as the existing analytical freefall gate.
    if(f.name!=='hover')for(let j=1;j<3;j++)expect(refinements[j].max.positionM,`${f.name}: position refinement`).toBeLessThan(refinements[j-1].max.positionM*.7);
    if(f.name==='differential')for(let j=1;j<3;j++)expect(refinements[j].max.attitudeRad).toBeLessThan(refinements[j-1].max.attitudeRad*.7);
    return {name:f.name,durationS:f.duration,initialPositionM:[0,0,20],initialVelocityMps:f.initialVelocity,
      duties:f.duties,directThrustN:f.directThrust,refinements};
  });
  const freefall=[120,240,480].map(hz=>{
    const w=new FlightWorld(DEFAULT_MODEL,false);w.setInitial([0,0,20]);
    const initialEnergyJ=DEFAULT_MODEL.mass*GRAVITY*20;
    for(let i=0;i<hz;i++)w.step(zero,1/hz,false);
    const result={hz,positionErrorM:Math.abs(w.position[2]-(20-GRAVITY/2)),velocityErrorMps:Math.abs(w.velocity[2]+GRAVITY),
      energyErrorJ:w.kinetic()+DEFAULT_MODEL.mass*GRAVITY*w.position[2]-initialEnergyJ};w.dispose();return result;
  });
  expect(freefall[1].positionErrorM).toBeLessThan(freefall[0].positionErrorM*.7);
  expect(freefall[2].positionErrorM).toBeLessThan(freefall[1].positionErrorM*.7);
  const p=new Powertrain();for(let i=0;i<2400;i++)p.step([.3+(i%100)/200,.45,.65,.4],1/240,4);
  const electrical=p.audit();
  expect(Math.abs(electrical.energyError)).toBeLessThan(1e-6);
  expect(Math.abs(electrical.sourceError)).toBeLessThan(1e-6);
  expect(Math.abs(electrical.chargeError)).toBeLessThan(1e-7);
  expect(Math.abs(electrical.thermalError)).toBeLessThan(1e-7);
  const contacts=([[[0,0,.3],[1,0,-3]],[[9,2.1,2],[5,0,0]]] as [V3,V3][]).map(([position,velocity])=>{
    const w=new FlightWorld(DEFAULT_MODEL,true);w.world.gravity={x:0,y:0,z:0};w.setInitial(position,velocity);
    const initialKineticJ=w.kinetic();let peakKineticJ=initialKineticJ;
    for(let i=0;i<180;i++){w.step(zero,1/240,false);peakKineticJ=Math.max(peakKineticJ,w.kinetic());}
    const result={position,velocity,initialKineticJ,peakKineticJ,finalKineticJ:w.kinetic(),contacts:w.contacts};w.dispose();
    expect(result.contacts).toBeGreaterThan(0);expect(peakKineticJ).toBeLessThanOrEqual(initialKineticJ+1e-4);return result;
  });
  const report={schema:'physical-fpv-numerical-evidence-v1',
    referenceCommit:fixtures.source_sha,syntheticParameters:true,hardwareValidated:false,browserRenderingTest:false,
    method:'Python RK4 reference vs Rapier Float32 rigid body. Same initial state and fixed inputs; sampled every 0.05 s. Powertrain midpoint SOC. No bitwise-equality claim.',
    limitsAt240Hz:limits,bodyRates:'Reported for diagnosis; no pre-established rate tolerance. Position/velocity/quaternion gates remain binding.',
    refinementNotes:'Three step sizes for all five trajectories against the pinned 240 Hz Python reference. Analytical zero-drag freefall requires decreasing position error. Non-hover position and differential attitude errors must shrink by a factor below 0.7 per halving of dt toward that fixed reference. This is not proof of convergence to exact real-world dynamics.',
    trajectories,analyticalFreefall:freefall,electricalTenSecondAudit:electrical,passiveContacts:contacts};
  const directory=fileURLToPath(new URL('../../docs/game-v0.1/evidence/',import.meta.url));mkdirSync(directory,{recursive:true});
  writeFileSync(directory+'numerical-report.json',JSON.stringify(report,null,2)+'\n');
});
