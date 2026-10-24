import {beforeAll,expect,it} from 'vitest';
import {mkdirSync,writeFileSync} from 'node:fs';
import {TransientPowertrain,TRANSIENT,G07_MODEL,G08_MODEL} from '../src/physics/transient';
import {Powertrain} from '../src/physics/powertrain';
import {DEFAULT_MODEL,RHO} from '../src/physics/config';
import {FlightWorld,initPhysics} from '../src/physics/world';
import {GameSession} from '../src/game/session';
import {ZERO} from '../src/physics/controller';
beforeAll(initPhysics);
const report:Record<string,unknown>={schema:'fpv-g08-evidence-v1',syntheticParameters:true,hardwareValidated:false,physicalPhoneValidated:false,parameters:TRANSIENT};
const save=()=>{mkdirSync('numerical-results',{recursive:true});writeFileSync('numerical-results/g08-transients.json',JSON.stringify(report,null,2)+'\n');};
it('starts at rest, has finite spin-up, current limiting, and passive coast-down without deleting rotor energy',()=>{
 const p=new TransientPowertrain(),steady=new Powertrain();expect(p.step([0,0,0,0],1/240).omega).toEqual([0,0,0,0]);
 const first=p.step([1,1,1,1],1/240);expect(first.omega[0]).toBeGreaterThan(0);expect(first.omega[0]).toBeLessThan(steady.evaluate([1,1,1,1]).omega[0]);expect(Math.max(...first.motorCurrent)).toBeLessThanOrEqual(60);
 const initial=first.omega[0];for(let i=0;i<240;i++)p.step([.6,.6,.6,.6],1/240);
 expect(p.last.omega[0]).toBeGreaterThan(initial);const before=p.last.omega[0],energy=p.audit().rotorKineticJ;
 const coast=p.step([0,0,0,0],1/240);expect(coast.omega[0]).toBeGreaterThan(0);expect(coast.omega[0]).toBeLessThan(before);expect(coast.current).toBe(0);expect(p.audit().rotorKineticJ).toBeLessThan(energy);
 for(let i=0;i<2400;i++)p.step([0,0,0,0],1/240);expect(p.last.omega[0]).toBeLessThan(before*.03);
 expect(Math.abs(p.audit().energyError)).toBeLessThan(1e-6);report.spinUpCoast={first,before,coast,audit:p.audit()};save();
});
it('closes ten-second varying-command energy including storage, charge and cell thermal ledger',()=>{
 const p=new TransientPowertrain();let maxPowerError=0,maxResidual=0;
 for(let i=0;i<2400;i++){const d=i%240<120?[.1,.8,.5,.4]:[0,.3,.9,.2];const o=p.step(d,1/240,4);maxPowerError=Math.max(maxPowerError,Math.abs(o.powerError));maxResidual=Math.max(maxResidual,Math.abs(o.residual));}
 const a=p.audit();expect(Math.abs(a.energyError)).toBeLessThan(1e-6);expect(Math.abs(a.sourceError)).toBeLessThan(1e-6);expect(Math.abs(a.chargeError)).toBeLessThan(1e-7);expect(Math.abs(a.thermalError)).toBeLessThan(1e-7);expect(maxPowerError).toBeLessThan(1e-6);expect(maxResidual).toBeLessThan(1e-10);report.tenSeconds={a,maxPowerError,maxResidual};save();
});
it('rejects invalid command, time and late depleted-SOC failure without partial mutation',()=>{
 const p=new TransientPowertrain();const original=JSON.stringify(p);
 for(const d of [[NaN,0,0,0],[2,0,0,0],[-1,0,0,0],[1]])expect(()=>p.step(d,1/240)).toThrow();
 for(const dt of [0,-1,.1,NaN])expect(()=>p.step([1,1,1,1],dt)).toThrow();expect(JSON.stringify(p)).toBe(original);
 p.soc=.0500000001;const depleted=JSON.stringify(p);expect(()=>p.step([1,1,1,1],.02)).toThrow();expect(JSON.stringify(p)).toBe(depleted);
});
it('converges to independent RK4 ODE for symmetric throttle with explicitly shrinking electrical step',()=>{
 // Independent time-domain ODE: scalar symmetric motors and algebraic bus solved by bisection.
 const m=DEFAULT_MODEL,J=TRANSIENT.motorInertia+m.propMass*m.diameter*m.diameter/12,r=.068,k=m.motorK;
 const tq=.012*RHO*m.diameter**5/(2*Math.PI)**2,C=m.capacityAh*3600;
 const deriv=([w,soc]:number[])=>{const ocv=4*(3.1+1.1*soc);let lo=0,hi=ocv,v=0,I=0,eff=0;
   for(let n=0;n<48;n++){v=(lo+hi)/2;I=Math.min(60,Math.max(0,(.7*v-k*w)/r));eff=I===0?0:(k*w+r*I)/v;if(v+.048*4*eff*I>ocv)hi=v;else lo=v;}
   return [(k*I-1e-6*w-tq*w*w)/J,-4*eff*I/C];};
 let y=[0,.9];const h=1/30720;
 for(let t=0;t<3072;t++){const a=deriv(y),b=deriv(y.map((x,i)=>x+h*a[i]/2)),c=deriv(y.map((x,i)=>x+h*b[i]/2)),d=deriv(y.map((x,i)=>x+h*c[i]));y=y.map((x,i)=>x+h*(a[i]+2*b[i]+2*c[i]+d[i])/6);}
 // External timesteps below the fixed internal bound expose actual midpoint refinement.
 const convergence=[1920,3840,7680].map(hz=>{const p=new TransientPowertrain();for(let i=0;i<hz/10;i++)p.step([.7,.7,.7,.7],1/hz);return {hz,omega:p.last.omega[0],soc:p.soc,error:Math.abs(p.last.omega[0]-y[0])};});
 expect(convergence[0].error).toBeLessThan(.1);expect(convergence[1].error).toBeLessThan(convergence[0].error*.7);expect(convergence[2].error).toBeLessThan(convergence[1].error*.7);
 report.independentRK4={reference:y,convergence};save();
});
it('reports same-condition G07/G08 flight and 120/240/480 Hz outcomes without altering old trajectory fixtures',()=>{
 const results=[];
 for(const kind of ['step','hover','cutoff','differential'] as const)for(const hz of [120,240,480])for(const version of [G07_MODEL,G08_MODEL]){
  const p=version===G08_MODEL?new TransientPowertrain():new Powertrain(),w=new FlightWorld(DEFAULT_MODEL,false);w.setInitial([0,0,20]);
  const hover=p.hover(),trace=[];
  for(let i=0;i<hz;i++){const time=i/hz;const d=kind==='hover'?Array(4).fill(hover):kind==='differential'?[.51,.49,.5,.5]:Array(4).fill(kind==='cutoff'&&time>=.5?0:.6);
   const load=p.step(d,1/hz);w.step(load,1/hz);if((i+1)%(hz/20)===0)trace.push({time:(i+1)/hz,position:w.position,velocity:w.velocity,rates:w.rates,omega:load.omega,energy:p.audit()});}
  expect(trace.every(t=>t.position.every(Number.isFinite))).toBe(true);expect(Math.abs(p.audit().energyError)).toBeLessThan(1e-6);results.push({kind,hz,version,trace});w.dispose();
 }
 for(const kind of ['step','hover','cutoff','differential']){const a=results.find(x=>x.kind===kind&&x.hz===240&&x.version===G07_MODEL)!,b=results.find(x=>x.kind===kind&&x.hz===240&&x.version===G08_MODEL)!;expect(a.trace[0].omega[0]).not.toBe(b.trace[0].omega[0]);}
 report.flightComparisons=results;save();
});
it('G08 is the player default, same-model replay agrees and legacy replay selects G07',()=>{
 const a=new GameSession();a.start();a.arm(0);for(let i=0;i<240;i++)a.step({...ZERO,throttle:.5});const replay=a.exportReplay('test'),end=a.snapshot();expect(replay.physicsModel).toBe(G08_MODEL);
 const b=new GameSession();b.replay(replay);for(let i=0;i<240;i++)b.step(ZERO);expect(b.snapshot().position).toEqual(end.position);expect(b.snapshot().rpm).toEqual(end.rpm);
 const legacy={...replay};delete legacy.physicsModel;b.replay(legacy);expect(b.physicsModel).toBe(G07_MODEL);expect(b.power).not.toBeInstanceOf(TransientPowertrain);
 const bad={...replay,physicsModel:'made-up'};expect(()=>b.replay(bad)).toThrow();a.world.dispose();b.world.dispose();
});
it('disarm cuts current but retains physical rotor energy; pause freezes it',()=>{
 const s=new GameSession();s.start();s.arm(0);for(let i=0;i<30;i++)s.step({...ZERO,throttle:.6});const before=(s.power as TransientPowertrain).rotorOmega;
 s.pause();expect(s.power.last.current).toBe(0);expect(s.power.last.omega).toEqual(before);const snap=JSON.stringify(s.snapshot());s.step(ZERO);expect(JSON.stringify(s.snapshot())).toBe(snap);s.world.dispose();
});
it('checks signed startup reaction, coasting friction, and rotor gyroscopic cross-product',()=>{
 const p=new TransientPowertrain(),load=p.step([.6,0,0,0],1/240);
 expect(load.reactionTorque[0]).toBeGreaterThan(load.torque[0]);
 expect(load.rotorAngularMomentum).toBeLessThan(0);
 const z=[0,0,0,0],results=[];
 for(const sign of [-1,1]){
  const w=new FlightWorld(DEFAULT_MODEL,false);w.setInitial([0,0,20],[0,0,0],[1,0,0,0],[0,0,0]);
  w.step({thrust:z,torque:z,reactionTorque:sign===1?[.01,0,0,0]:[0,.01,0,0]},1/240,false);
  expect(Math.sign(w.rates[2])).toBe(sign);results.push({kind:'reaction',sign,rates:w.rates});w.dispose();
  const g=new FlightWorld(DEFAULT_MODEL,false);g.setInitial([0,0,20],[0,0,0],[1,0,0,0],[1,0,0]);
  g.step({thrust:z,torque:z,rotorAngularMomentum:sign*.001},1/240,false);
  expect(Math.sign(g.rates[1])).toBe(sign);results.push({kind:'gyro',sign,rates:g.rates});g.dispose();
 }
 const coast=p.step(z,1/240);expect(coast.reactionTorque[0]).toBeLessThan(0);
 report.signedMoments={startup:load,coast,results};save();
});
it('keeps a sixty-second synthetic powertrain run inside energy, temperature, and speed bounds',()=>{
 const p=new TransientPowertrain();let maxW=0,maxEnergyError=0;
 for(let i=0;i<3000;i++){p.step([.45,.45,.45,.45],.02,2);maxW=Math.max(maxW,...p.last.omega);maxEnergyError=Math.max(maxEnergyError,Math.abs(p.audit().energyError));}
 expect(maxEnergyError).toBeLessThan(1e-6);expect(p.temperature).toBeLessThan(333.15);expect(p.soc).toBeGreaterThan(.05);
 report.longRun={durationSeconds:60,dt:.02,audit:p.audit(),maxW,maxEnergyError,temperature:p.temperature,soc:p.soc};save();
});
it('isolates G07 and G08 best times without overwriting legacy storage',async()=>{
 const {loadBest,saveBest,BEST_KEY}=await import('../src/game/session');
 const map=new Map<string,string>([[BEST_KEY,'12']]),storage={getItem:(k:string)=>map.get(k)??null,setItem:(k:string,v:string)=>{map.set(k,v);}};
 expect(loadBest(storage,G08_MODEL)).toBeNull();saveBest(storage,9,G08_MODEL);expect(loadBest(storage,G08_MODEL)).toBe(9);expect(loadBest(storage,G07_MODEL)).toBe(12);expect(map.get(BEST_KEY)).toBe('12');
});
it('defines sustained locked-rotor bench separately from unsupported aerodynamic stall',async()=>{
 const {lockedRotorBench}=await import('../src/physics/transient');
 const cases=[0,.1,.5,1].map(duty=>({duty,result:lockedRotorBench(Array(4).fill(duty))}));
 for(const c of cases){expect(c.result.omega).toEqual([0,0,0,0]);expect(Math.max(...c.result.motorCurrent)).toBeLessThanOrEqual(60);expect(Math.abs(c.result.powerError)).toBeLessThan(1e-8);}
 expect(cases[3].result.motorCurrent).toEqual([60,60,60,60]);
 report.stallComparison={definition:'externally clamped stationary rotor circuit, zero mechanical work',G07:'UNSUPPORTED: algebraic solver cannot represent a locked rotor; unchanged',G08:cases,aerodynamicBladeStall:'NOT IMPLEMENTED',hardware:'NOT VALIDATED'};save();
});
it('all sixteen synthetic assemblies preserve transient finite-state and energy bounds',async()=>{
 const {assemblyModel}=await import('../src/physics/config');
 const rows=[];
 for(const frame of ['trainer','light'] as const)for(const battery of ['standard','endurance'] as const)for(const motor of ['balanced','torque'] as const)for(const propeller of ['5inch','4inch'] as const){
  const assembly={frame,battery,motor,propeller},p=new TransientPowertrain(assemblyModel(assembly));
  for(let i=0;i<120;i++)p.step(i<60?[1,1,1,1]:[0,0,0,0],1/240);
  expect(Math.abs(p.audit().energyError)).toBeLessThan(1e-6);expect(p.last.omega.every(x=>x>=0&&x<5000)).toBe(true);rows.push({assembly,omega:p.last.omega,energy:p.audit()});
 }
 report.assemblies=rows;save();
});
