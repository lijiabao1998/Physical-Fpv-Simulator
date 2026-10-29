import { DEFAULT_ASSEMBLY,FIXED_DT,assemblyModel,type Assembly } from '../physics/config';
import { FlightWorld } from '../physics/world';
import { Powertrain } from '../physics/powertrain';
import {TransientPowertrain,G07_MODEL,G08_MODEL,type PhysicsModel} from '../physics/transient';
import { ZERO,motorDuties,validateControls,type Controls,type FlightMode } from '../physics/controller';
import { norm,type V3 } from '../physics/math';
import {getCourse,type CourseId} from './courses';
import { Course,COURSE_VERSION } from './course';

export type SessionState='ready'|'flying'|'paused'|'crashed'|'finished'|'replay';
export interface ReplayEvent { c:Controls; a:boolean; m:FlightMode; r:number }
export interface ReplayBundle {
  schema:'physical-fpv-replay-v1';courseId?:CourseId;courseVersion?:string;physicsModel?:PhysicsModel;version:'0.1.0';build:string;dt:number;assembly:Assembly;practice:boolean;events:ReplayEvent[];
}
const MAX_EVENTS=144000;
export class GameSession {
  world:FlightWorld;power:Powertrain;course:Course;
  state:SessionState='ready';armed=false;mode:FlightMode='angle';time=0;airtime=0;rate=3.5;
  rotorPhases=[0,0,0,0];
  reason='Throttle to zero. Hold ARM to confirm.';lastControls:Controls={...ZERO};
  private imported=false;
  /** Replay provenance survives pause/resume; only an explicit fresh reset is local. */
  get recordable(){return !this.imported;}
  events:ReplayEvent[]=[];private replayEvents:ReplayEvent[]|null=null;private replayIndex=0;
  constructor(public assembly:Assembly={...DEFAULT_ASSEMBLY},public practice=true,public physicsModel:PhysicsModel=G08_MODEL,public courseId:CourseId='training-straight') {
    const model=assemblyModel(assembly);this.world=new FlightWorld(model,true,this.courseId);this.power=this.physicsModel===G08_MODEL?new TransientPowertrain(model):new Powertrain(model);this.course=new Course(practice,this.courseId);
  }
  start() {if(this.state==='ready'){this.state='flying';this.reason='Ready. Zero throttle, then hold ARM.';}}
  arm(throttle:number) {
    if(this.state!=='flying')return false;
    if(!Number.isFinite(throttle)||throttle>.025||throttle<0){this.reason='ARM blocked: lower throttle to zero.';return false;}
    if(this.power.soc<.06){this.reason='Battery depleted. Retry for a fresh synthetic pack.';return false;}
    this.armed=true;this.reason='Armed. Raise throttle gently.';return true;
  }
  disarm(reason='Disarmed') {
    this.armed=false;this.lastControls={...ZERO};this.power.last=this.power instanceof TransientPowertrain?this.power.coastOutput():this.power.evaluate([0,0,0,0]);this.reason=reason;
    this.world.body.resetForces(true);this.world.body.resetTorques(true);
  }
  fail(reason:string) {this.disarm(reason);if(['flying','replay'].includes(this.state))this.state='paused';}
  pause() {
    if(this.state==='flying'||this.state==='replay'){this.disarm('Paused and disarmed. Resume, then ARM again.');this.state='paused';}
    else if(this.state==='paused'){this.replayEvents=null;this.state='flying';this.reason='Resumed, disarmed. Hold ARM with zero throttle.';}
  }
  reset(assembly=this.assembly,practice=this.practice) {
    this.world.dispose();this.assembly={...assembly};this.practice=practice;
    const model=assemblyModel(assembly);this.world=new FlightWorld(model,true,this.courseId);this.power=this.physicsModel===G08_MODEL?new TransientPowertrain(model):new Powertrain(model);this.course=new Course(practice,this.courseId);
    this.imported=false;this.armed=false;this.time=0;this.airtime=0;this.rotorPhases=[0,0,0,0];this.state='flying';this.events=[];this.lastControls={...ZERO};this.replayEvents=null;this.replayIndex=0;
    this.reason='Fresh pack. Zero throttle, then hold ARM.';
  }
  step(input:Controls,dt=FIXED_DT) {
    if(!['flying','replay'].includes(this.state))return;
    let c=input;
    if(this.replayEvents) {
      const event=this.replayEvents[this.replayIndex++];
      if(!event){this.state='finished';this.disarm('Replay finished. Retry to fly.');return;}
      c=event.c;this.armed=event.a;this.mode=event.m;this.rate=event.r;
    }
    validateControls(c);
    if(!this.replayEvents&&this.events.length>=MAX_EVENTS){this.fail('Ten-minute recording limit. Export replay and retry.');return;}
    const command=this.armed?{...c}:{...ZERO};
    if(!this.replayEvents)this.events.push({c:{...command},a:this.armed,m:this.mode,r:this.rate});
    this.lastControls=command;
    try {
      const previous=this.world.position,previousQ=this.world.quaternion;
      const duties=this.armed?motorDuties(this.world.quaternion,this.world.rates,command,this.mode,this.rate):[0,0,0,0];
      const load=this.power.step(duties,dt,norm(this.world.velocity));
      this.world.step(load,dt);this.time+=dt;
      this.rotorPhases=this.rotorPhases.map((phase,i)=>(phase+(i%2===0?-1:1)*load.omega[i]*dt)%(2*Math.PI));
      if(this.armed)this.airtime+=dt;
      this.course.update(previous,this.world.position,this.time,dt,previousQ,this.world.quaternion);
      if(this.world.contact&&this.world.impactSpeed>3.5) {
        this.course.invalidate();this.state='crashed';this.disarm(`Impact at ${this.world.impactSpeed.toFixed(1)} m/s. Retry to fly again.`);
      }
      if(this.course.finishedAt!==null){this.state='finished';this.disarm('Course complete. Best time saved locally when storage is available.');}
      if(this.power.soc<.055)this.fail('Synthetic pack depleted — stopped and disarmed. Retry.');
      if(Math.abs(this.world.position[0])>220||Math.abs(this.world.position[1])>220||this.world.position[2]>180||this.world.position[2]<-5){this.course.invalidate();this.fail('Training boundary reached — paused. Retry.');}
    } catch(error) {this.fail(`Physics guard: ${(error as Error).message}. Retry.`);}
  }
  exportReplay(build:string):ReplayBundle {
    return {schema:'physical-fpv-replay-v1',courseId:this.courseId,courseVersion:getCourse(this.courseId).version,physicsModel:this.physicsModel,version:'0.1.0',build,dt:FIXED_DT,assembly:{...this.assembly},practice:this.practice,events:structuredClone(this.events)};
  }
  replay(bundle:unknown) {
    const b=bundle as ReplayBundle;
    if(!b||b.schema!=='physical-fpv-replay-v1'||b.version!=='0.1.0'||b.dt!==FIXED_DT||!Array.isArray(b.events)||!b.events.length||b.events.length>MAX_EVENTS||typeof b.practice!=='boolean')throw Error('Unsupported or oversized replay');
    if(b.physicsModel!==undefined&&b.physicsModel!==G07_MODEL&&b.physicsModel!==G08_MODEL)throw Error('Unknown physics model');
    if(b.courseId&&b.courseId!=='training-straight'&&typeof b.courseVersion!=='string')throw Error('New-course replay requires its version');
    const selected=getCourse(b.courseId??'training-straight',b.courseVersion??(b.courseId?undefined:COURSE_VERSION));
    assemblyModel(b.assembly);
    for(const e of b.events){validateControls(e.c);if(typeof e.a!=='boolean'||!['angle','acro'].includes(e.m)||!Number.isFinite(e.r)||e.r<1||e.r>10)throw Error('Invalid replay event');}
    const events=structuredClone(b.events);
    this.courseId=selected.id;this.physicsModel=b.physicsModel??G07_MODEL;this.reset(b.assembly,b.practice);this.imported=true;this.replayEvents=events;this.replayIndex=0;this.state='replay';this.reason='Input replay — same build/runtime only; no hardware claim.';
  }
  switchCourse(id:string){const c=getCourse(id);this.disarm('Course changed');this.courseId=c.id;this.reset();}
  snapshot() {
    return {courseId:this.courseId,courseVersion:getCourse(this.courseId).version,physicsModel:this.physicsModel,state:this.state,armed:this.armed,mode:this.mode,time:this.time,airtime:this.airtime,
      position:this.world.position,velocity:this.world.velocity,quaternion:this.world.quaternion,rates:this.world.rates,
      voltage:this.power.last.voltage,current:this.power.last.current,soc:this.power.soc,
      thrust:[...this.power.last.thrust],rpm:[...this.power.last.rpm],contacts:this.world.contacts,
      splits:structuredClone(this.course.splits),courseValid:!this.course.invalid,gate:this.course.next,courseTime:this.course.elapsed(this.time),reason:this.reason,energy:this.power.audit(),mass:this.world.model.mass};
  }
}
export const BEST_KEY='physical-fpv-course-best-v1';
export function loadBest(storage: Pick<Storage,'getItem'>,model:PhysicsModel=G07_MODEL): number|null {
  try{const raw=storage.getItem(model===G07_MODEL?BEST_KEY:BEST_KEY+'-'+model);if(!raw)return null;const n=Number(raw);return Number.isFinite(n)&&n>0?n:null;}catch{return null;}
}
export function saveBest(storage:Pick<Storage,'getItem'|'setItem'>,time:number,model:PhysicsModel=G07_MODEL) {
  if(!Number.isFinite(time)||time<=0)return null;
  const current=loadBest(storage,model),best=current===null?time:Math.min(time,current);
  try{storage.setItem(model===G07_MODEL?BEST_KEY:BEST_KEY+'-'+model,String(best));return best;}catch{return null;}
}
/** Contact/crash is an explicit game rule; collision impulses are still Rapier's. */
export const ZERO_POSITION: V3=[0,0,.105];
