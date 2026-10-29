import {beforeAll,it,expect} from 'vitest';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {initPhysics} from '../src/physics/world';
import {GameSession} from '../src/game/session';
import {ZERO} from '../src/physics/controller';
import {FIXED_DT} from '../src/physics/config';
import {G07_MODEL,G08_MODEL} from '../src/physics/transient';
import {COURSES,getCourse,type CourseId} from '../src/game/courses';
import {rotate,clamp,euler} from '../src/physics/math';
import {saveRecord} from '../src/game/records';
import {planPhysicsSteps} from '../src/game/timing';
import {GhostPlayback,GhostRecorder,ghostClass,ghostKey,loadGhost,saveGhost,ghostPoseAt,gateComparisons,MAX_GHOST_SAMPLES,MAX_GHOST_BYTES} from '../src/game/ghost';
beforeAll(initPhysics);
const storage=()=>{const map=new Map<string,string>();return {map,getItem:(k:string)=>map.get(k)??null,setItem:(k:string,v:string)=>{map.set(k,v);}};};
function localLap(courseId:CourseId='british-slalom',observe=true,damping=2){
 const s=new GameSession(undefined,true,undefined,courseId),r=new GhostRecorder();s.start();s.arm(0);if(observe)r.observe(s);let phase=0,gate=0,hover=s.power.hover();const trace=[];
 for(let tick=0;tick<240*110&&s.state==='flying';tick++){
  const g=getCourse(s.courseId).gates[gate],n=rotate(g.rotation,[1,0,0]),p=s.world.position,v=s.world.velocity;
  const target=g.center.map((x,k)=>x+(phase===0?-3:3)*n[k]);if(phase===0&&Math.hypot(...target.map((x,k)=>x-p[k]))<.6)phase=1;
  if(s.course.next>gate){gate=s.course.next;phase=0;if(gate>=getCourse(s.courseId).gates.length)break;}
  const [roll,pitch,yaw]=euler(s.world.quaternion),a=target.map((x,k)=>clamp(1.3*(x-p[k])-damping*v[k],-3,3));
  const ax=Math.cos(yaw)*a[0]+Math.sin(yaw)*a[1],ay=-Math.sin(yaw)*a[0]+Math.cos(yaw)*a[1],dy=Math.atan2(Math.sin(Math.atan2(n[1],n[0])-yaw),Math.cos(Math.atan2(n[1],n[0])-yaw));
  if(tick%120===0)hover=s.power.hover();
  const c={throttle:clamp(hover*Math.sqrt((9.80665+a[2])/(9.80665*Math.max(.4,Math.cos(roll)*Math.cos(pitch)))),.05,.8),pitch:clamp(Math.atan2(ax,9.80665+a[2])/.6,-1,1),roll:clamp(-Math.atan2(ay,9.80665+a[2])/.6,-1,1),yaw:clamp(dy*.8,-.4,.4)};
  s.step(c);if(observe)r.observe(s);trace.push({tick:tick+1,position:s.world.position,quaternion:s.world.quaternion,contacts:s.world.contacts,splits:structuredClone(s.course.splits)});
 }
 expect(s.state).toBe('finished');expect(s.course.invalid).toBe(false);return {s,r,trace};
}
let fixture:ReturnType<typeof localLap>|undefined;
const getFixture=()=>fixture??=localLap();
it('G11 replay origin remains non-recordable after pause and resume',()=>{
 const s=new GameSession();s.start();s.step(ZERO);const b=s.exportReplay('test');s.replay(b);
 expect(s.recordable).toBe(false);s.pause();s.pause();expect(s.recordable).toBe(false);s.reset();expect(s.recordable).toBe(true);s.world.dispose();
});
it.each(['training-straight','british-slalom','industrial-run'] as const)('G11 full input-only %s PB has exact original simulation poses and bounded timeline',courseId=>{
 const f=courseId==='british-slalom'?getFixture():localLap(courseId),g=f.r.completed(f.s,'g11-test')!;expect(g).not.toBeNull();expect(g.poses.length).toBeLessThanOrEqual(MAX_GHOST_SAMPLES);
 for(const p of g.poses.slice(1)){expect(p.position).toEqual(f.trace[p.tick-1].position);expect(p.quaternion).toEqual(f.trace[p.tick-1].quaternion);}
 const store=storage();saveRecord(store,g.physicsModel,g.assembly,g,g.courseVersion);expect(saveGhost(store,g,g)).toBe(true);expect(loadGhost(store,g)).toEqual(g);
 const bytes=JSON.stringify(g).length*2;expect(bytes).toBeLessThan(MAX_GHOST_BYTES);
 mkdirSync('numerical-results',{recursive:true});writeFileSync(`numerical-results/g11-${courseId}.json`,JSON.stringify({scope:'Synthetic controls-only navigator through original mixer/Rapier. No body writes; not human or hardware acceptance.',ghost:g,replay:f.s.exportReplay('g11-test'),end:f.s.snapshot(),poseSamples:g.poses.length,utf16Bytes:bytes},null,2));
 if(courseId!=='british-slalom')f.s.world.dispose();
},30000);
it('G11 ghost observation/sample rendering leaves every player state, event, collision, energy and split exactly unchanged',()=>{
 const withGhost=getFixture(),withoutGhost=localLap('british-slalom',false);
 expect(withGhost.s.snapshot()).toEqual(withoutGhost.s.snapshot());expect(withGhost.s.events).toEqual(withoutGhost.s.events);expect(withGhost.trace).toEqual(withoutGhost.trace);
 const g=withGhost.r.completed(withGhost.s,'same')!,before=JSON.stringify(withGhost.s.snapshot()),events=JSON.stringify(withGhost.s.events),tape=JSON.stringify(g);
 const world=withGhost.s.world.world,bodies=world.bodies.len(),colliders=world.colliders.len();
 for(let i=0;i<10000;i++)ghostPoseAt(g,(i%5000)/100);expect(JSON.stringify(withGhost.s.snapshot())).toBe(before);expect(JSON.stringify(withGhost.s.events)).toBe(events);expect(JSON.stringify(g)).toBe(tape);expect(world.bodies.len()).toBe(bodies);expect(world.colliders.len()).toBe(colliders);
 withoutGhost.s.world.dispose();
},30000);
it('G11 exact input replay and ghost alignment agree at 60/20/5 Hz without another ghost physics body',()=>{
 const f=getFixture(),g=f.r.completed(f.s,'same')!,bundle=f.s.exportReplay('same'),results=[];
 for(const hz of [60,20,5]){const s=new GameSession();s.replay(bundle);let accumulator=0,tick=0;const nodes=[];
 while(tick<bundle.events.length){const p=planPhysicsSteps(accumulator,1/hz,true);expect(p.fault).toBeNull();accumulator=p.remainder;for(let i=0;i<p.steps&&tick<bundle.events.length;i++,tick++){s.step(ZERO);if((tick+1)%4===0||tick+1===bundle.events.length){const pose=g.poses[Math.ceil((tick+1)/4)];expect(s.world.position).toEqual(pose.position);expect(s.world.quaternion).toEqual(pose.quaternion);}if((tick+1)%48===0)nodes.push(ghostPoseAt(g,s.course.elapsed(s.time)));}}
 expect(s.snapshot().position).toEqual(f.s.snapshot().position);expect(s.snapshot().energy).toEqual(f.s.snapshot().energy);expect(s.course.splits).toEqual(f.s.course.splits);expect(s.events).toEqual([]);results.push({hz,nodes,end:s.snapshot()});s.world.dispose();}
 expect(results[1].nodes).toEqual(results[0].nodes);expect(results[2].nodes).toEqual(results[0].nodes);
 writeFileSync('numerical-results/g11-timing.json',JSON.stringify({dt:FIXED_DT,results},null,2));
},30000);
it('G11 all 96 exact classes and unknown course/version/physics/assembly reject cross-class ghosts',()=>{
 const f=getFixture(),g=f.r.completed(f.s,'same')!,store=storage();saveRecord(store,g.physicsModel,g.assembly,g,g.courseVersion);saveGhost(store,g,g);const before=JSON.stringify([...store.map]);let negatives=0;
 for(const course of COURSES)for(const model of [G07_MODEL,G08_MODEL])for(const frame of ['trainer','light'] as const)for(const battery of ['standard','endurance'] as const)for(const motor of ['balanced','torque'] as const)for(const propeller of ['5inch','4inch'] as const){const c={courseId:course.id,courseVersion:course.version,physicsModel:model,assembly:{frame,battery,motor,propeller}};if(ghostKey(c)===ghostKey(g))expect(loadGhost(store,c)).toEqual(g);else{expect(loadGhost(store,c)).toBeNull();expect(saveGhost(store,c,g)).toBe(false);negatives++;}}
 for(const c of [{...g,courseId:'missing'},{...g,courseVersion:'future'},{...g,physicsModel:'future'},{...g,assembly:{...g.assembly,frame:undefined}}])expect(loadGhost(store,c as any)).toBeNull();
 expect(negatives).toBe(95);expect(JSON.stringify([...store.map])).toBe(before);
});
it('G11 legacy, malformed, missing identity, invalid pose/splits and oversized/quota records fail closed without writes',()=>{
 const f=getFixture(),g=f.r.completed(f.s,'same')!,store=storage();saveRecord(store,g.physicsModel,g.assembly,g,g.courseVersion);store.map.set('physical-fpv-course-best-v1','12.000');
 expect(loadGhost(store,g)).toBeNull();const raw=JSON.stringify([...store.map]);
 const bads:any[]=[{},null,{...g,schema:'legacy'},{...g,courseVersion:undefined},{...g,assembly:undefined},{...g,source:'imported'},{...g,total:NaN},{...g,sourceTicks:144001},{...g,splits:g.splits.slice(1)},{...g,poses:g.poses.slice(1)},{...g,poses:[{...g.poses[0],position:[NaN,0,0]},...g.poses.slice(1)]},{...g,poses:[{...g.poses[0],quaternion:[0,0,0,0]},...g.poses.slice(1)]},{...g,poses:Array(MAX_GHOST_SAMPLES+1).fill(g.poses[0])}];
 for(const bad of bads)expect(saveGhost(store,g,bad)).toBe(false);expect(JSON.stringify([...store.map])).toBe(raw);
 for(const value of ['null','{}','bad',' '.repeat(MAX_GHOST_BYTES)])expect(loadGhost({getItem:()=>value},g)).toBeNull();
 expect(saveGhost({...store,setItem:()=>{throw Error('quota');}},g,g)).toBe(false);expect(store.getItem('physical-fpv-course-best-v1')).toBe('12.000');
});
it('G11 unfinished, crashed, imported, reset, missing-tick and invalid sources cannot produce Ghost',()=>{
 const s=new GameSession(),r=new GhostRecorder();r.observe(s);s.start();s.step(ZERO);r.observe(s);expect(r.completed(s,'same')).toBeNull();
 s.world.setInitial([0,0,2],[0,0,-12]);while(s.state==='flying'){s.step(ZERO);r.observe(s);}expect(s.state).toBe('crashed');expect(r.completed(s,'same')).toBeNull();
 s.reset();r.observe(s);expect(r.sampleCount).toBe(1);s.arm(0);s.step(ZERO);s.step(ZERO);r.observe(s);expect(r.sampleCount).toBe(0);expect(r.completed(s,'same')).toBeNull();
 const f=getFixture();s.replay(f.s.exportReplay('same'));r.observe(s);for(let i=0;i<f.s.events.length;i++){s.step(ZERO);r.observe(s);}expect(s.state).toBe('finished');expect(r.completed(s,'same')).toBeNull();s.world.dispose();
});
it('G11 pause/reset/retry and course switch freeze/reset/unload timeline without sampling render time',()=>{
 const s=new GameSession(),r=new GhostRecorder(),g=getFixture().r.completed(getFixture().s,'same')!;s.start();r.observe(s);for(let i=0;i<120;i++){s.step(ZERO);r.observe(s);}
 s.pause();const before=s.snapshot(),pose=ghostPoseAt(g,s.course.elapsed(s.time)),count=r.sampleCount;for(let i=0;i<240;i++){s.step(ZERO);r.observe(s);expect(ghostPoseAt(g,s.course.elapsed(s.time))).toEqual(pose);}expect(s.snapshot()).toEqual(before);expect(r.sampleCount).toBe(count);
 s.reset();r.observe(s);expect(r.sampleCount).toBe(1);expect(s.time).toBe(0);s.switchCourse('industrial-run');r.observe(s);expect(ghostClass(s).courseId).toBe('industrial-run');expect(r.sampleCount).toBe(1);expect(s.time).toBe(0);s.world.dispose();
});
it('G11 completed repeated gates/slower candidate and mismatching current PB cannot overwrite Ghost bytes',()=>{
 const f=getFixture(),g=f.r.completed(f.s,'same')!,store=storage();saveRecord(store,g.physicsModel,g.assembly,g,g.courseVersion);saveGhost(store,g,g);const before=JSON.stringify([...store.map]);
 for(let i=0;i<100;i++){f.s.step(ZERO);f.r.observe(f.s);}expect(f.r.completed(f.s,'same')).toEqual(g);expect(saveGhost(store,g,g)).toBe(true);expect(JSON.stringify([...store.map])).toBe(before);
 const faster={total:g.total/2,splits:g.splits.map(s=>({...s,elapsed:s.elapsed/2,sector:s.sector/2}))};saveRecord(store,g.physicsModel,g.assembly,faster,g.courseVersion);expect(loadGhost(store,g)).toBeNull();expect(saveGhost(store,g,g)).toBe(false);
 expect(store.getItem(ghostKey(g))).toBe(JSON.parse(before).find(([k]:string[])=>k===ghostKey(g))[1]);
});
it('G11 gate deltas use same ordered crossing only, no continuous path estimate',()=>{
 const g=getFixture().r.completed(getFixture().s,'same')!,player=g.splits.slice(0,3).map((s,i)=>({...s,elapsed:s.elapsed+(i===1?-.42:i===2?.31:0)}));
 const compare=gateComparisons(player,g);expect(compare).toHaveLength(3);expect(compare[1].delta).toBeCloseTo(-.42,12);expect(compare[2].delta).toBeCloseTo(.31,12);expect(gateComparisons(player,null).every(x=>x.delta===null&&x.pb===null)).toBe(true);
});
it('G11 ghost source has no Rapier/input/RNG/scoring mutator and original physics remains byte-identical',()=>{
 const source=readFileSync('src/game/ghost.ts','utf8');for(const forbidden of ['new FlightWorld','new GameSession','Math.random','world.step(','course.update(','setTranslation','setLinvel','motorDuties'])expect(source).not.toContain(forbidden);
 expect(FIXED_DT).toBe(1/240);expect(planPhysicsSteps(0,.251,true).steps).toBe(0);
});

it('G11 two actual completed local laps replace a slower PB Ghost only after a genuine faster finish',()=>{
 const slow=localLap('british-slalom',true,2.3),fast=getFixture(),a=slow.r.completed(slow.s,'g11-test')!,b=fast.r.completed(fast.s,'g11-test')!,store=storage();
 expect(a.total).toBeGreaterThan(b.total);saveRecord(store,a.physicsModel,a.assembly,a,a.courseVersion);expect(saveGhost(store,a,a)).toBe(true);expect(loadGhost(store,a)!.total).toBe(a.total);
 saveRecord(store,b.physicsModel,b.assembly,b,b.courseVersion);expect(saveGhost(store,b,b)).toBe(true);expect(loadGhost(store,b)!.total).toBe(b.total);
 writeFileSync('numerical-results/g11-slow-british-slalom.json',JSON.stringify({scope:'Second ordinary-input navigator variant, increased velocity damping; same original physics.',ghost:a,replay:slow.s.exportReplay('g11-test'),end:slow.s.snapshot(),improvementSeconds:a.total-b.total},null,2));slow.s.world.dispose();
},30000);

it('G11 paused visual cache reuses immutable pose and invalidates on time, identity and reset',()=>{
 const f=getFixture(),g=f.r.completed(f.s,'cache-test')!,c=new GhostPlayback(),raw=JSON.stringify(g);
 const first=c.sample(g,1);for(let i=0;i<10000;i++)expect(c.sample(g,1)).toBe(first);
 const next=c.sample(g,1+FIXED_DT);expect(next).not.toBe(first);expect(next).toEqual(ghostPoseAt(g,1+FIXED_DT));
 const replacement=structuredClone(g),changed=c.sample(replacement,1+FIXED_DT);expect(changed).not.toBe(next);expect(changed).toEqual(next);
 c.clear();expect(c.sample(replacement,1+FIXED_DT)).not.toBe(changed);expect(c.sample(g,0)).toEqual(ghostPoseAt(g,0));
 expect(JSON.stringify(g)).toBe(raw);expect(JSON.stringify(replacement)).toBe(raw);
});
