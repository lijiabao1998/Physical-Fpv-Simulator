import {beforeAll,it,expect} from 'vitest';
import {Course,COURSE_VERSION} from '../src/game/course';
import {GATES} from '../src/game/field';
import {recordKey,loadRecord,saveRecord} from '../src/game/records';
import {DEFAULT_ASSEMBLY,type Assembly,FIXED_DT} from '../src/physics/config';
import {G07_MODEL,G08_MODEL} from '../src/physics/transient';
import {GameSession,BEST_KEY} from '../src/game/session';
import {initPhysics} from '../src/physics/world';
import {ZERO} from '../src/physics/controller';
import {planPhysicsSteps} from '../src/game/timing';
beforeAll(initPhysics);
const cross=(c:Course,i:number,time:number)=>{const g=GATES[i];return c.update([g.center[0]-1,g.center[1],g.center[2]],[g.center[0]+1,g.center[1],g.center[2]],time,.02);};
const completed=()=>{const c=new Course();GATES.forEach((_,i)=>cross(c,i,i+1));return c;};
it('G09 ordered splits sum exactly; backwards, skipped, outside and repeated gates do not score',()=>{
 const c=new Course();expect(cross(c,1,1)).toBe(false);
 const g=GATES[0];expect(c.update([11,0,2.1],[9,0,2.1],1,.02)).toBe(false);
 expect(c.update([9,10,2.1],[11,10,2.1],1,.02)).toBe(false);
 expect(cross(c,0,1)).toBe(true);expect(cross(c,0,1.1)).toBe(false);
 GATES.slice(1).forEach((_,i)=>cross(c,i+1,i+2));c.splits.forEach((x,i)=>expect(x.elapsed).toBeCloseTo(i,12));
 expect(c.splits.reduce((n,x)=>n+x.sector,0)).toBe(c.elapsed(10));
 expect(cross(c,4,12)).toBe(false);expect(c.splits).toHaveLength(5);
 expect(g.width).toBeGreaterThan(0);
});
it('G09 collision invalidates a run permanently; free flight never scores',()=>{
 const c=completed();c.invalidate();expect(c.finishedAt).toBeNull();expect(cross(c,4,20)).toBe(false);
 expect(cross(new Course(false),0,1)).toBe(false);
});
it('G09 all 32 physics/assembly classes isolate records and retain unknown legacy keys',()=>{
 const map=new Map([[BEST_KEY,'12'],[BEST_KEY+'-'+G08_MODEL,'15'],['unrelated','safe']]);
 const storage={getItem:(k:string)=>map.get(k)??null,setItem:(k:string,v:string)=>{map.set(k,v);}};
 const keys=new Set<string>();const c=completed(),record={total:4,splits:c.splits};
 for(const frame of ['trainer','light'] as const)for(const battery of ['standard','endurance'] as const)for(const motor of ['balanced','torque'] as const)for(const propeller of ['5inch','4inch'] as const)for(const model of [G07_MODEL,G08_MODEL]){
 const a:Assembly={frame,battery,motor,propeller};keys.add(recordKey(model,a));expect(loadRecord(storage,model,a)).toBeNull();expect(saveRecord(storage,model,a,record)?.total).toBe(4);expect(loadRecord(storage,model,a)).toEqual(record);
 }
 expect(keys.size).toBe(32);expect(map.get(BEST_KEY)).toBe('12');expect(map.get(BEST_KEY+'-'+G08_MODEL)).toBe('15');expect(map.get('unrelated')).toBe('safe');
 expect(()=>recordKey(G08_MODEL,DEFAULT_ASSEMBLY,'unknown')).toThrow();
});
it('G09 malformed, incomplete, mismatched splits and unavailable storage fail closed',()=>{
 for(const raw of ['null','{}','bad','{"total":2,"splits":[]}'])expect(loadRecord({getItem:()=>raw},G08_MODEL,DEFAULT_ASSEMBLY)).toBeNull();
 const c=completed();const storage={getItem:()=>null,setItem:()=>{throw Error('quota');}};
 expect(saveRecord(storage,G08_MODEL,DEFAULT_ASSEMBLY,{total:4,splits:c.splits})).toBeNull();
 expect(saveRecord(storage,G08_MODEL,DEFAULT_ASSEMBLY,{total:3,splits:c.splits})).toBeNull();
});
it('G09 session pause freezes splits/time, reset clears them, replay validates course before mutation',()=>{
 const s=new GameSession();s.start();cross(s.course,0,1);s.pause();const t=s.time;s.step(ZERO);expect(s.time).toBe(t);expect(s.course.splits).toHaveLength(1);
 s.pause();s.step(ZERO);const b=s.exportReplay('test');expect(b.courseVersion).toBe(COURSE_VERSION);
 expect(()=>s.replay({...b,courseVersion:'future'})).toThrow('Unknown course');expect(s.course.splits).toHaveLength(1);
 s.reset();expect(s.course.splits).toEqual([]);expect(s.course.invalid).toBe(false);
 s.replay({...b,courseVersion:undefined});expect(s.course.splits).toEqual([]);s.world.dispose();
});
it('G09 fixed-step replay and 60/20 FPS scheduling preserve event time and trajectory',()=>{
 const run=(frameDt:number)=>{const s=new GameSession();s.start();let accumulator=0;for(let i=0;i<Math.round(1/frameDt);i++){const plan=planPhysicsSteps(accumulator,frameDt,true);accumulator=plan.remainder;expect(plan.fault).toBeNull();for(let j=0;j<plan.steps;j++)s.step(ZERO);}return s;};
 const a=run(1/60),b=run(1/20);expect(a.time).toBeCloseTo(b.time,12);expect(a.world.position).toEqual(b.world.position);
 const r=new GameSession();r.replay(a.exportReplay('test'));for(let i=0;i<a.events.length;i++)r.step(ZERO,FIXED_DT);expect(r.world.position).toEqual(a.world.position);expect(r.course.splits).toEqual(a.course.splits);
 a.world.dispose();b.world.dispose();r.world.dispose();
});
it('G09 scheduled forward crossing events are identical at 60 and 20 FPS',()=>{
 const run=(frameDt:number)=>{const c=new Course();let acc=0,tick=0;for(let frame=0;frame<Math.round(5/frameDt);frame++){const p=planPhysicsSteps(acc,frameDt,true);acc=p.remainder;for(let j=0;j<p.steps;j++){tick++;if(tick%240===0)cross(c,tick/240-1,tick*FIXED_DT);}}return c;};
 const a=run(1/60),b=run(1/20);expect(a.next).toBe(5);expect(a.splits).toEqual(b.splits);expect(a.finishedAt).toBe(b.finishedAt);
});
it('G09 actual Rapier collision invalidates an unfinished timed run and reset restores eligibility',()=>{
 const s=new GameSession();s.start();cross(s.course,0,1);s.world.setInitial([0,0,2],[0,0,-12]);
 for(let i=0;i<100&&s.state!=='crashed';i++)s.step(ZERO);
 expect(s.state).toBe('crashed');expect(s.course.invalid).toBe(true);expect(s.course.finishedAt).toBeNull();expect(s.course.splits).toHaveLength(1);
 s.reset();expect(s.course.invalid).toBe(false);expect(s.course.splits).toEqual([]);s.world.dispose();
});
it('G09 malformed record ordering, NaN and faster valid record handling preserve prior bytes',()=>{
 const map=new Map<string,string>();const storage={getItem:(k:string)=>map.get(k)??null,setItem:(k:string,v:string)=>{map.set(k,v);}};
 const c=completed(),record={total:4,splits:c.splits};saveRecord(storage,G08_MODEL,DEFAULT_ASSEMBLY,record);const before=map.get(recordKey(G08_MODEL,DEFAULT_ASSEMBLY));
 expect(saveRecord(storage,G08_MODEL,DEFAULT_ASSEMBLY,{...record,total:NaN})).toBeNull();
 const bad=structuredClone(record);bad.splits[1].gate=5;expect(saveRecord(storage,G08_MODEL,DEFAULT_ASSEMBLY,bad)).toBeNull();
 expect(map.get(recordKey(G08_MODEL,DEFAULT_ASSEMBLY))).toBe(before);
 const slower={total:8,splits:record.splits.map(s=>({...s,elapsed:s.elapsed*2,sector:s.sector*2}))};expect(saveRecord(storage,G08_MODEL,DEFAULT_ASSEMBLY,slower)).toEqual(record);expect(map.get(recordKey(G08_MODEL,DEFAULT_ASSEMBLY))).toBe(before);
});
