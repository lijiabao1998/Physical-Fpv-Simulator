import {FIXED_DT,type Assembly} from '../physics/config';
import type {PhysicsModel} from '../physics/transient';
import type {V3,Q4} from '../physics/math';
import type {GameSession} from './session';
import {getCourse,type CourseId} from './courses';
import {recordKey,loadRecord,type RaceRecord} from './records';

export const GHOST_SCHEMA='physical-fpv-pb-ghost-v1';
export const MAX_GHOST_TICKS=144000,MAX_GHOST_SAMPLES=36002,MAX_GHOST_BYTES=4*1024*1024;
export interface GhostClass {courseId:CourseId;courseVersion:string;physicsModel:PhysicsModel;assembly:Assembly}
/** Snapshot of an existing player state, not a second simulated aircraft. */
export interface GhostPose {tick:number;position:V3;quaternion:Q4}
export interface GhostRecord extends GhostClass,RaceRecord {
 schema:typeof GHOST_SCHEMA;dt:number;sampleEveryTicks:4;build:string;
 source:'local-completed-fixed-step';sourceTicks:number;startedAt:number;finishedAt:number;poses:GhostPose[];
}
type ReadStorage=Pick<Storage,'getItem'>;
type WriteStorage=Pick<Storage,'getItem'|'setItem'>;
export function ghostClass(s:GameSession):GhostClass{return {courseId:s.courseId,courseVersion:getCourse(s.courseId).version,physicsModel:s.physicsModel,assembly:{...s.assembly}};}
export function ghostKey(c:GhostClass){getCourse(c.courseId,c.courseVersion);return `${GHOST_SCHEMA}:${recordKey(c.physicsModel,c.assembly,c.courseVersion)}`;}
const classEqual=(a:GhostClass,b:GhostClass)=>a.courseId===b.courseId&&a.courseVersion===b.courseVersion&&a.physicsModel===b.physicsModel&&(['frame','battery','motor','propeller'] as const).every(k=>a.assembly?.[k]===b.assembly?.[k]);
const sameRace=(a:RaceRecord,b:RaceRecord)=>a.total===b.total&&JSON.stringify(a.splits)===JSON.stringify(b.splits);
function valid(record:GhostRecord,c:GhostClass){
 try{
  ghostKey(c);
  if(!record||record.schema!==GHOST_SCHEMA||!classEqual(record,c)||record.source!=='local-completed-fixed-step'||record.dt!==FIXED_DT||record.sampleEveryTicks!==4||typeof record.build!=='string'||!record.build||record.build.length>128)return false;
  if(!Number.isInteger(record.sourceTicks)||record.sourceTicks<1||record.sourceTicks>MAX_GHOST_TICKS||!Number.isFinite(record.startedAt)||!Number.isFinite(record.finishedAt)||record.startedAt<0||record.finishedAt<=record.startedAt||Math.abs(record.finishedAt-record.startedAt-record.total)>1e-9)return false;
  if(record.finishedAt>record.sourceTicks*FIXED_DT+1e-7||record.finishedAt<(record.sourceTicks-1)*FIXED_DT-1e-7)return false;
  // Reuse G09's strict split validator without writing or interpreting legacy keys.
  if(!loadRecord({getItem:()=>JSON.stringify({total:record.total,splits:record.splits})},c.physicsModel,c.assembly,c.courseVersion))return false;
  const poses=record.poses;
  if(!Array.isArray(poses)||poses.length<2||poses.length>MAX_GHOST_SAMPLES||poses[0].tick!==0||poses.at(-1)!.tick!==record.sourceTicks)return false;
  return poses.every((p,i)=>p&&Number.isInteger(p.tick)&&p.tick>=0&&p.tick<=MAX_GHOST_TICKS&&(!i||(p.tick>poses[i-1].tick&&p.tick-poses[i-1].tick<=4))&&(i===poses.length-1||p.tick%4===0)&&Array.isArray(p.position)&&p.position.length===3&&p.position.every(v=>Number.isFinite(v)&&Math.abs(v)<1000)&&Array.isArray(p.quaternion)&&p.quaternion.length===4&&p.quaternion.every(Number.isFinite)&&Math.abs(Math.hypot(...p.quaternion)-1)<1e-4);
 }catch{return false;}
}
/** Observer has no reference to physics mutators and samples only completed fixed ticks. */
export class GhostRecorder {
 private course:GameSession['course']|null=null;private poses:GhostPose[]=[];private lastTick=0;private eligible=false;
 observe(s:GameSession){
  if(this.course!==s.course){this.course=s.course;this.poses=[];this.lastTick=0;this.eligible=s.recordable&&s.time===0&&s.events.length===0;if(this.eligible)this.capture(s,0);}
  if(!this.eligible)return;
  const tick=s.events.length;
  if(!s.recordable||s.course.invalid||tick>MAX_GHOST_TICKS||Math.abs(s.time-tick*FIXED_DT)>1e-7||tick<this.lastTick||tick>this.lastTick+1){this.eligible=false;this.poses=[];return;}
  if(tick===this.lastTick)return;
  this.lastTick=tick;
  if(tick%4===0||s.course.finishedAt!==null)this.capture(s,tick);
 }
 private capture(s:GameSession,tick:number){this.poses.push({tick,position:[...s.world.position],quaternion:[...s.world.quaternion]});}
 completed(s:GameSession,build:string):GhostRecord|null{
  if(!this.eligible||this.course!==s.course||!s.recordable||!s.practice||s.state!=='finished'||s.course.invalid||s.course.startedAt===null||s.course.finishedAt===null||this.lastTick!==s.events.length)return null;
  const r:GhostRecord={...ghostClass(s),schema:GHOST_SCHEMA,dt:FIXED_DT,sampleEveryTicks:4,source:'local-completed-fixed-step',build,sourceTicks:this.lastTick,startedAt:s.course.startedAt,finishedAt:s.course.finishedAt,total:s.course.elapsed(s.time),splits:structuredClone(s.course.splits),poses:structuredClone(this.poses)};
  return valid(r,ghostClass(s))?r:null;
 }
 get sampleCount(){return this.poses.length;}
}
/** A Ghost is usable only when its explicitly identified record still IS the class PB. */
export function loadGhost(storage:ReadStorage,c:GhostClass):GhostRecord|null{
 try{const raw=storage.getItem(ghostKey(c));if(!raw||raw.length*2>MAX_GHOST_BYTES)return null;const r=JSON.parse(raw) as GhostRecord;
  if(!valid(r,c))return null;const pb=loadRecord(storage,c.physicsModel,c.assembly,c.courseVersion);return pb&&sameRace(r,pb)?r:null;
 }catch{return null;}
}
export function saveGhost(storage:WriteStorage,c:GhostClass,r:GhostRecord):boolean{
 try{if(!valid(r,c))return false;const pb=loadRecord(storage,c.physicsModel,c.assembly,c.courseVersion);if(!pb||!sameRace(r,pb))return false;
  const previous=loadGhost(storage,c);if(previous&&previous.total<=r.total)return true;
  const raw=JSON.stringify(r);if(raw.length*2>MAX_GHOST_BYTES)return false;storage.setItem(ghostKey(c),raw);return true;
 }catch{return false;}
}
/** Binary search and shortest-arc normalized interpolation: visual only, never dt integration. */
export function ghostPoseAt(record:GhostRecord,lapElapsed:number):GhostPose{
 const tick=Math.max(0,Math.min(record.total,Number.isFinite(lapElapsed)?lapElapsed:0))/FIXED_DT+record.startedAt/FIXED_DT;
 const poses=record.poses;let lo=0,hi=poses.length-1;
 while(hi-lo>1){const mid=(lo+hi)>>1;if(poses[mid].tick<=tick)lo=mid;else hi=mid;}
 const a=poses[lo],b=poses[hi],t=Math.max(0,Math.min(1,(tick-a.tick)/(b.tick-a.tick)));
 const sign=a.quaternion.reduce((v,x,i)=>v+x*b.quaternion[i],0)<0?-1:1;
 const q=a.quaternion.map((x,i)=>x+(sign*b.quaternion[i]-x)*t) as Q4,n=Math.hypot(...q);
 return {tick,position:a.position.map((x,i)=>x+(b.position[i]-x)*t) as V3,quaternion:q.map(x=>x/n) as Q4};
}
export function gateComparisons(player:RaceRecord['splits'],pb:RaceRecord|null){return player.map(s=>({gate:s.gate,player:s.elapsed,pb:pb?.splits[s.gate-1]?.elapsed??null,delta:pb?.splits[s.gate-1]?s.elapsed-pb.splits[s.gate-1].elapsed:null}));}

/** Single-entry visual cache: paused or repeated reads do not allocate/search again.
 * Identity/time invalidation and explicit unload never alter the saved record. */
export class GhostPlayback {
 private record:GhostRecord|null=null;private elapsed=NaN;private pose:GhostPose|null=null;
 sample(record:GhostRecord,lapElapsed:number):GhostPose{
  const elapsed=Math.max(0,Math.min(record.total,Number.isFinite(lapElapsed)?lapElapsed:0));
  if(record!==this.record||elapsed!==this.elapsed){this.record=record;this.elapsed=elapsed;this.pose=ghostPoseAt(record,elapsed);}
  return this.pose!;
 }
 clear(){this.record=null;this.elapsed=NaN;this.pose=null;}
}
