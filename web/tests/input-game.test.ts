import {beforeAll,describe,it,expect} from 'vitest';
import {InputManager,type PadLike} from '../src/input/manager';
import {cloneSettings,shapeAxis,validatedSettings,saveSettings,loadSettings} from '../src/input/settings';
import {initPhysics} from '../src/physics/world';
import {GameSession,loadBest,saveBest} from '../src/game/session';
import {Course} from '../src/game/course';
import {GATES} from '../src/game/field';
import {ZERO} from '../src/physics/controller';

beforeAll(async()=>{await initPhysics();});
type MutablePad = Omit<PadLike,'axes'|'buttons'> & {axes:number[];buttons:{value:number;pressed:boolean}[]};
const pad=(id='Xbox Wireless Controller'):MutablePad=>({id,index:0,connected:true,mapping:'standard',axes:[0,0,0,0],buttons:Array.from({length:17},()=>({pressed:false,value:0})),timestamp:0});
const memory=()=>{const map=new Map<string,string>();return {getItem:(k:string)=>map.get(k)??null,setItem:(k:string,v:string)=>{map.set(k,v);}};};
describe('C: controller API, calibration and fail-safe (no physical hardware)',()=>{
  it.each(['Xbox Wireless Controller','DualSense Wireless Controller','Standard generic'])('%s standard console mapping and hold-to-arm',id=>{
    const p=pad(id),input=new InputManager(cloneSettings(),()=>{});input.sample([p],.01,0);
    p.buttons[0]={value:1,pressed:true};
    expect(input.sample([p],.01,10).actions).not.toContain('arm');
    expect(input.sample([p],.01,611).actions).toContain('arm');
    expect(input.sample([p],.01,800).actions).not.toContain('arm');
    p.buttons[7]={value:.65,pressed:true};p.axes=[.5,0,.4,-.6];
    const f=input.sample([p],.01,900);expect(f.controls.throttle).toBe(.65);expect(f.controls.roll).toBeGreaterThan(0);expect(f.controls.pitch).toBeGreaterThan(0);expect(f.controls.yaw).toBeLessThan(0);
    p.buttons[1]={value:1,pressed:true};p.buttons[3]={value:1,pressed:true};p.buttons[9]={value:1,pressed:true};
    expect(input.sample([p],.01,1000).actions).toEqual(['disarm','camera','pause']);
  });
  it('never ARM with nonzero held trigger and rejects unknown mapping',()=>{
    const p=pad(),input=new InputManager(cloneSettings(),()=>{});p.buttons[0]={value:1,pressed:true};p.buttons[7]={value:.5,pressed:true};
    input.sample([p],.1,0);expect(input.sample([p],.1,1000).actions).not.toContain('arm');
    p.mapping='';expect(input.sample([p],.1,1100).supported).toBe(false);
  });
  it('Mode 2 integrated centered throttle stays zero; absolute center is explicit half duty',()=>{
    const settings=cloneSettings();settings.layout='mode2';const p=pad(),i=new InputManager(settings,()=>{});
    expect(i.sample([p],.02,0).controls.throttle).toBe(0);p.axes=[0,-1,0,0];
    for(let n=0;n<50;n++)i.sample([p],.02,n*20);
    p.axes=[0,0,0,0];expect(i.sample([p],.02,1100).controls.throttle).toBeCloseTo(.55);
    settings.throttleMode='absolute';expect(i.sample([p],.02,1200).controls.throttle).toBe(.5);
  });
  it('calibration centers, full-scale, inversion, deadzone and expo are applied and persist',()=>{
    const s=cloneSettings();s.axes.roll={index:1,center:.1,min:-.9,max:.9,inverted:true};
    expect(shapeAxis(.1,s.axes.roll,.08,.5)).toBe(0);expect(shapeAxis(.9,s.axes.roll,.08,.5)).toBe(-1);
    expect(Math.abs(shapeAxis(.5,s.axes.roll,.08,.8))).toBeLessThan(Math.abs(shapeAxis(.5,s.axes.roll,.08,0)));
    const store=memory();expect(saveSettings(store,s)).toBe(true);expect(loadSettings(store)).toEqual(s);
    expect(validatedSettings({deadzone:NaN,rate:100,axes:null}).rate).toBe(10);
    expect(loadSettings({getItem:()=>'{oops'})).toEqual(cloneSettings());
  });
  it('disconnect, replacement and invalid data clear stale commands immediately',()=>{
    const reasons:string[]=[];const i=new InputManager(cloneSettings(),r=>reasons.push(r)),p=pad();
    i.sample([p],.02,0);p.buttons[7]={value:.7,pressed:true};i.sample([p],.02,20);
    expect(i.sample([], .02,40).controls).toEqual(ZERO);expect(reasons.at(-1)).toContain('disconnected');
    p.axes=[NaN,0,0,0];expect(i.sample([p],.02,50).controls).toEqual(ZERO);
  });
  it('frozen nonzero timestamps disarm while changing timestamps continue',()=>{
    const reasons:string[]=[];const i=new InputManager(cloneSettings(),r=>reasons.push(r)),p=pad();p.timestamp=1;
    for(let n=0;n<25;n++)i.sample([p],.1,n*100);
    expect(reasons.at(-1)).toContain('stale');
  });
});
describe('game flow, course and reproducible replay',()=>{
  it('validates ordered apertures, direction and exact crossing times',()=>{
    const c=new Course();
    expect(c.update([11,0,2],[9,0,2],1,.1)).toBe(false);
    expect(c.update([9,10,2],[11,10,2],1,.1)).toBe(false);
    GATES.forEach((g,n)=>expect(c.update([g.center[0]-1,g.center[1],g.center[2]],[g.center[0]+1,g.center[1],g.center[2]],n+1,.1)).toBe(true));
    expect(c.next).toBe(5);expect(c.elapsed(100)).toBeCloseTo(4);
  });
  it('goes ready -> armed -> takeoff -> pause/disarm -> retry, no zero-throttle surprise',()=>{
    const g=new GameSession();expect(g.arm(0)).toBe(false);g.start();expect(g.arm(.1)).toBe(false);expect(g.arm(0)).toBe(true);
    for(let n=0;n<300;n++)g.step({...ZERO,throttle:.47});
    expect(g.world.position[2]).toBeGreaterThan(.5);expect(g.airtime).toBeGreaterThan(1);
    g.fail('Browser lost focus');expect(g.armed).toBe(false);expect(g.state).toBe('paused');expect(g.power.last.current).toBe(0);
    const t=g.time;g.step({...ZERO,throttle:1});expect(g.time).toBe(t);
    g.reset();expect(g.time).toBe(0);expect(g.armed).toBe(false);expect(g.power.soc).toBe(.9);g.world.dispose();
  });
  it('replays actual saved fixed-step inputs with identical same-runtime state',()=>{
    const g=new GameSession();g.start();g.arm(0);
    for(let n=0;n<300;n++)g.step({...ZERO,throttle:.45,pitch:n>180?.07:0});
    const end=g.snapshot(),bundle=g.exportReplay('test');
    g.replay(bundle);for(let n=0;n<bundle.events.length;n++)g.step(ZERO);
    const after=g.snapshot();expect(after.position).toEqual(end.position);expect(after.quaternion).toEqual(end.quaternion);expect(after.soc).toBe(end.soc);
    expect(()=>g.replay({...bundle,dt:.1})).toThrow();g.world.dispose();
  });
  it('physical crash preserves contact result then retry resets without reloading',()=>{
    const g=new GameSession();g.start();g.world.setInitial([0,0,1],[0,0,-5]);
    for(let n=0;n<100&&g.state==='flying';n++)g.step(ZERO);
    expect(g.state).toBe('crashed');expect(g.armed).toBe(false);expect(g.world.contacts).toBeGreaterThan(0);
    g.reset();expect(g.state).toBe('flying');expect(g.world.contacts).toBe(0);g.world.dispose();
  });
  it('local course best improves only; denied storage is harmless',()=>{
    const s=memory();expect(loadBest(s)).toBeNull();expect(saveBest(s,10)).toBe(10);expect(saveBest(s,12)).toBe(10);expect(saveBest(s,8)).toBe(8);
    expect(saveBest({getItem:()=>null,setItem:()=>{throw Error('blocked');}},5)).toBeNull();
  });
});


describe('input audit regressions',()=>{
  it('same-index device replacement resets ARM hold and announces fail-safe',()=>{
    const reasons:string[]=[],input=new InputManager(cloneSettings(),r=>reasons.push(r));
    const xbox=pad(),ps5=pad('DualSense Wireless Controller');
    input.sample([xbox],.01,0);xbox.buttons[0]={value:1,pressed:true};input.sample([xbox],.01,1);
    ps5.buttons[0]={value:1,pressed:true};
    const replacement=input.sample([ps5],.01,650);
    expect(reasons.some(r=>r.includes('replaced'))).toBe(true);
    expect(replacement.actions).not.toContain('arm');
    expect(input.sample([ps5],.01,1251).actions).toContain('arm');
  });
  it('hostile calibration ranges stay bounded and invalid live settings fail closed',()=>{
    for(const center of [-.5,0,.5]){
      const s=validatedSettings({axes:{roll:{index:2,center,min:-1e30,max:1e30,inverted:true}}});
      const axis=s.axes.roll;expect(axis.min).toBe(-1);expect(axis.max).toBe(1);
      for(const raw of [-1,-.5,0,.5,1])expect(Math.abs(shapeAxis(raw,axis,s.deadzone,s.expo))).toBeLessThanOrEqual(1);
    }
    const a=cloneSettings().axes.roll;
    expect(shapeAxis(0,{...a,min:0,max:0},.1,.2)).toBe(0);
    expect(shapeAxis(.5,a,1,.2)).toBe(0);expect(shapeAxis(.5,a,.1,NaN)).toBe(0);
    expect(validatedSettings({axes:{roll:{index:2,center:0,min:0,max:0}}}).axes.roll).toEqual(a);
  });
});


it('rotor phase follows fixed simulation time, freezes while paused, and replays exactly',()=>{
  const g=new GameSession();g.start();g.arm(0);
  for(let n=0;n<120;n++)g.step({...ZERO,throttle:.45});
  const phases=[...g.rotorPhases],bundle=g.exportReplay('test');
  expect(phases.some(p=>p!==0)).toBe(true);g.pause();
  for(let n=0;n<120;n++)g.step({...ZERO,throttle:1});
  expect(g.rotorPhases).toEqual(phases);
  g.replay(bundle);for(let n=0;n<bundle.events.length;n++)g.step(ZERO);
  expect(g.rotorPhases).toEqual(phases);g.reset();expect(g.rotorPhases).toEqual([0,0,0,0]);g.world.dispose();
});
