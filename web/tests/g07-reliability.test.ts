import {describe,it,expect} from 'vitest';
import {InputManager,type PadLike} from '../src/input/manager';
import {cloneSettings} from '../src/input/settings';
type Pad=Omit<PadLike,'axes'|'buttons'>&{axes:number[];buttons:{value:number;pressed:boolean}[]};
const pad=(id:string):Pad=>({id,index:0,connected:true,mapping:'standard',timestamp:1,axes:[0,0,0,0],buttons:Array.from({length:17},()=>({value:0,pressed:false}))});
describe('G07 API simulation, hardware untested',()=>{
  for(const id of ['Xbox Wireless Controller','DualSense Wireless Controller']){
    it(`${id}: 60 seconds unchanged timestamp is not disconnect`,()=>{
      const errors:string[]=[],m=new InputManager(cloneSettings(),r=>errors.push(r)),p=pad(id);
      m.sample([p],1/60,0);errors.length=0;p.buttons[7].value=.45;p.axes=[.1,0,.2,-.2];
      for(let n=1;n<=3600;n++){const f=m.sample([p],1/60,n*1000/60);expect(f.controls.throttle).toBe(.45);}
      expect(errors).toEqual([]);
    });
    it(`${id}: held ARM on connection and reconnection requires release`,()=>{
      const m=new InputManager(cloneSettings(),()=>{}),p=pad(id);p.buttons[0]={value:1,pressed:true};
      m.sample([p],.01,0);expect(m.sample([p],.01,700).actions).not.toContain('arm');
      p.buttons[0]={value:0,pressed:false};m.sample([p],.01,710);
      p.buttons[0]={value:1,pressed:true};m.sample([p],.01,720);
      expect(m.sample([p],.01,1320).actions).toContain('arm');
      m.sample([], .01,1330);m.sample([p],.01,1340);
      expect(m.sample([p],.01,2100).actions).not.toContain('arm');
    });
  }
});

it.each(['Xbox Wireless Controller','DualSense Wireless Controller'])('%s: ten minutes API input, mapping, index and fail-safe transitions',id=>{
 const errors:string[]=[],m=new InputManager(cloneSettings(),r=>errors.push(r)),p=pad(id);p.index=3;
 m.sample([null,null,null,p],1/60,0);errors.length=0;
 for(let n=1;n<=36000;n++){
   p.axes=[Math.sin(n/100)*.5,0,Math.cos(n/200)*.4,-.1];p.buttons[7].value=.4;
   if(n%1000===0)p.timestamp+=1;
   const f=m.sample([null,null,null,p],1/60,n*1000/60);
   expect(f.supported).toBe(true);expect(f.controls.throttle).toBe(.4);
 }
 expect(errors).toEqual([]);
 p.connected=false;expect(m.sample([p],.01,600010).controls.throttle).toBe(0);
 expect(errors.at(-1)).toContain('disconnected');p.connected=true;p.buttons[7].value=0;
 p.buttons[0]={value:1,pressed:true};m.sample([p],.01,600020);
 expect(m.sample([p],.01,601020).actions).not.toContain('arm');
 p.buttons[0]={value:0,pressed:false};m.sample([p],.01,601030);
 p.buttons[0]={value:1,pressed:true};m.sample([p],.01,601040);
 expect(m.sample([p],.01,601640).actions).toContain('arm');
 for(const reason of ['Window lost focus','Page hidden','Pause','Retry']){
   m.fail(reason);expect(m.sample([p],.01,602500).actions).not.toContain('arm');
   expect(m.sample([p],.01,603500).actions).not.toContain('arm');
 }
 p.mapping='';expect(m.sample([p],.01,604000).supported).toBe(false);
 p.mapping='standard';p.axes[0]=NaN;expect(m.sample([p],.01,604100).supported).toBe(false);
 p.axes=[0,0,0,0];m.settings.axes.roll.index=7;expect(m.sample([p],.01,604200).supported).toBe(false);
});

import {FlightDiagnostics} from '../src/game/diagnostics';
it('diagnostics are optional, bounded and separate render/physics costs',()=>{
 const d=new FlightDiagnostics();d.record(20,4,4,3);expect(d.snapshot().samples).toBe(0);
 d.setEnabled(true);for(let n=0;n<1000;n++)d.record(20,4,4,3);
 expect(d.snapshot()).toMatchObject({samples:240,fps:50,frameMs:20,physicsStepMs:1,renderCpuMs:3,lastSteps:4,maxSteps:4});
 d.record(NaN,1,1,1);expect(d.snapshot().samples).toBe(240);
 d.lastStop='Page hidden';d.setEnabled(false);expect(d.snapshot()).toMatchObject({samples:0,enabled:false,lastStop:'Page hidden'});
});
