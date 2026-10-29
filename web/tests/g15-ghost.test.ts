import {beforeAll,it,expect} from 'vitest';
import {initPhysics} from '../src/physics/world';
import {GameSession} from '../src/game/session';
import {ZERO} from '../src/physics/controller';
import {FIXED_DT} from '../src/physics/config';
import {getCourse,type CourseId} from '../src/game/courses';
import {rotate,clamp,euler} from '../src/physics/math';
import {saveRecord,recordKey} from '../src/game/records';
import {GhostRecorder,ghostKey,loadGhost,saveGhost,ghostPoseAt,type GhostRecord} from '../src/game/ghost';
beforeAll(initPhysics);

// G15 frozen numbers (docs/game-v0.1/G15-pb-ghost-release-fixes.md), hard-coded on purpose.
const BUDGET=2*1024*1024,QUOTA=5242880,PREFIX='physical-fpv-pb-ghost-v1:';
const ruleTick=(startedAt:number)=>4*Math.floor(startedAt/FIXED_DT/4);
const entryBytes=(k:string,v:string)=>(k.length+v.length)*2;

/** One shared origin: a Chromium-style quota over key plus value code units, and other games' keys. */
function origin(quota=QUOTA,foreign=true){
 const map=new Map<string,string>();const used=()=>[...map].reduce((n,[k,v])=>n+k.length+v.length,0);
 const s={map,getItem:(k:string)=>map.has(k)?map.get(k)!:null,
  setItem(k:string,v:string){const old=map.has(k)?k.length+map.get(k)!.length:0;if(used()-old+k.length+v.length>quota)throw new DOMException('quota','QuotaExceededError');map.set(k,String(v));},
  removeItem:(k:string)=>{map.delete(k);},key:(i:number)=>[...map.keys()][i]??null,get length(){return map.size;}};
 if(foreign){map.set('glimmertown-lab-save','{"city":"'+'x'.repeat(600000)+'"}');map.set('glimmertown-lab-save_bak','{"city":"'+'y'.repeat(600000)+'"}');
  map.set('defendtaipei-progress-v1','{"wave":12}');map.set('physical-fpv-settings-v1','{"rate":3.5}');map.set('physical-fpv-ui-lang-v1','zh-TW');}
 return s;
}
const ghostTotal=(s:ReturnType<typeof origin>)=>[...s.map].filter(([k])=>k.startsWith(PREFIX)).reduce((n,[k,v])=>n+entryBytes(k,v),0);
const others=(s:ReturnType<typeof origin>)=>JSON.stringify([...s.map].filter(([k])=>!k.startsWith(PREFIX)));
const orderOf=(raw:string|null)=>Number(/^\{"order":(\d+),/.exec(raw??'')?.[1]??NaN);

/** G11's ordinary-control navigator (g11-ghost.test.ts), with an optional disarmed idle before the lap. */
function lap(courseId:CourseId='british-slalom',damping=2,idleTicks=0){
 const s=new GameSession(undefined,true,undefined,courseId),r=new GhostRecorder();s.start();r.observe(s);
 const start={position:s.world.position,quaternion:s.world.quaternion};const trace:{tick:number;position:number[];quaternion:number[]}[]=[];
 for(let i=0;i<idleTicks;i++){s.step(ZERO);r.observe(s);trace.push({tick:i+1,position:s.world.position,quaternion:s.world.quaternion});}
 s.arm(0);let phase=0,gate=0,hover=s.power.hover();
 for(let tick=0;tick<240*110&&s.state==='flying';tick++){
  const g=getCourse(s.courseId).gates[gate],n=rotate(g.rotation,[1,0,0]),p=s.world.position,v=s.world.velocity;
  const target=g.center.map((x,k)=>x+(phase===0?-3:3)*n[k]);if(phase===0&&Math.hypot(...target.map((x,k)=>x-p[k]))<.6)phase=1;
  if(s.course.next>gate){gate=s.course.next;phase=0;if(gate>=getCourse(s.courseId).gates.length)break;}
  const [roll,pitch,yaw]=euler(s.world.quaternion),a=target.map((x,k)=>clamp(1.3*(x-p[k])-damping*v[k],-3,3));
  const ax=Math.cos(yaw)*a[0]+Math.sin(yaw)*a[1],ay=-Math.sin(yaw)*a[0]+Math.cos(yaw)*a[1],dy=Math.atan2(Math.sin(Math.atan2(n[1],n[0])-yaw),Math.cos(Math.atan2(n[1],n[0])-yaw));
  if(tick%120===0)hover=s.power.hover();
  const c={throttle:clamp(hover*Math.sqrt((9.80665+a[2])/(9.80665*Math.max(.4,Math.cos(roll)*Math.cos(pitch)))),.05,.8),pitch:clamp(Math.atan2(ax,9.80665+a[2])/.6,-1,1),roll:clamp(-Math.atan2(ay,9.80665+a[2])/.6,-1,1),yaw:clamp(dy*.8,-.4,.4)};
  s.step(c);r.observe(s);trace.push({tick:idleTicks+tick+1,position:s.world.position,quaternion:s.world.quaternion});
 }
 expect(s.state).toBe('finished');expect(s.course.invalid).toBe(false);return {s,r,trace,start};
}
const laps=new Map<string,ReturnType<typeof lap>>();
const fixture=(courseId:CourseId='british-slalom',damping=2)=>{const k=courseId+damping;if(!laps.has(k))laps.set(k,lap(courseId,damping));return laps.get(k)!;};
const ghostOf=(f:ReturnType<typeof lap>)=>f.r.completed(f.s,'g15-test')!;
const asClass=(g:GhostRecord,frame:'trainer'|'light',battery:'standard'|'endurance',motor:'balanced'|'torque'='balanced'):GhostRecord=>({...g,assembly:{...g.assembly,frame,battery,motor}});
function savePB(store:ReturnType<typeof origin>,g:GhostRecord){expect(saveRecord(store,g.physicsModel,g.assembly,{total:g.total,splits:g.splits},g.courseVersion)).not.toBeNull();}

it.each(['training-straight','british-slalom','industrial-run'] as const)('G15 U1 %s Ghost stores only the lap window',courseId=>{
 const f=fixture(courseId),g=ghostOf(f);expect(g).not.toBeNull();
 const first=ruleTick(g.startedAt);expect(first).toBeGreaterThan(0);
 expect(g.poses[0].tick).toBe(first);
 for(const p of g.poses){const t=f.trace[p.tick-1];expect(t.tick).toBe(p.tick);expect(p.position).toEqual(t.position);expect(p.quaternion).toEqual(t.quaternion);}
 const full=[{tick:0,...f.start},...f.trace.filter(t=>t.tick%4===0||t.tick===g.sourceTicks)];
 const untrimmed={...g,poses:full} as GhostRecord;
 for(const at of [0,g.total/2,g.total])expect(ghostPoseAt(g,at)).toEqual(ghostPoseAt(untrimmed,at));
 const count=f.r.sampleCount,again=ghostOf(f);expect(f.r.sampleCount).toBe(count);expect(again).toEqual(g);
},30000);

it('G15 U2 the validator requires the lap-window first tick and nothing else changes',()=>{
 const f=fixture(),g=ghostOf(f),first=ruleTick(g.startedAt),store=origin();savePB(store,g);
 const full=[{tick:0,...f.start},...f.trace.filter(t=>t.tick%4===0||t.tick===g.sourceTicks)];
 const before=JSON.stringify([...store.map]);
 // Twin accepted by the frozen rule, checked on a copy so the negatives start from an empty Ghost slot.
 const twin=origin();savePB(twin,g);expect(saveGhost(twin,g,g)).toBe(true);
 const untrimmed={...g,poses:full.filter(p=>p.tick>=0)} as GhostRecord;
 expect(saveGhost(store,g,untrimmed)).toBe(false);
 expect(saveGhost(store,g,{...g,poses:g.poses.slice(1)})).toBe(false);
 expect(saveGhost(store,g,{...g,poses:[{...g.poses[0],tick:first+1},...g.poses.slice(1)]})).toBe(false);
 // Shift the lap by 0.1 tick so the rule's tick moves by 4 while total, splits and sourceTicks stay valid.
 const d=.1*FIXED_DT,shifted={...g,startedAt:g.startedAt+d,finishedAt:g.finishedAt+d} as GhostRecord;
 expect(ruleTick(shifted.startedAt)).toBe(first+4);expect(shifted.finishedAt).toBeLessThanOrEqual(g.sourceTicks*FIXED_DT);
 expect(saveGhost(store,g,shifted)).toBe(false);expect(JSON.stringify([...store.map])).toBe(before);
 const control={...shifted,poses:shifted.poses.slice(1)} as GhostRecord;expect(control.poses[0].tick).toBe(first+4);
 expect(saveGhost(store,g,control)).toBe(true);
});

it('G15 U3 a lap after 175 s of idle from reset still stores its Ghost',()=>{
 const f=lap('training-straight',2,42000),g=ghostOf(f);expect(g).not.toBeNull();expect(g.startedAt).toBeGreaterThan(175);
 const store=origin();savePB(store,g);expect(saveGhost(store,g,g)).toBe(true);expect(loadGhost(store,g)).toEqual(g);
 f.s.world.dispose();
},120000);

it('G15 U4 the 2 MiB budget writes first, then removes the oldest other Ghosts and nothing else',()=>{
 const slow=ghostOf(fixture('british-slalom',2.3)),fast=ghostOf(fixture());expect(fast.total).toBeLessThan(slow.total);
 const store=origin(),foreign=others(store);
 const A=asClass(slow,'light','standard'),B=asClass(slow,'trainer','endurance'),C=asClass(slow,'light','endurance');
 for(const g of [A,B,C])savePB(store,g);const pbs=others(store);
 expect(saveGhost(store,A,A)).toBe(true);expect(saveGhost(store,B,B)).toBe(true);expect(ghostTotal(store)).toBeLessThanOrEqual(BUDGET);
 // A again with a faster lap: same key, highest order.
 const A2={...asClass(fast,'light','standard')};savePB(store,A2);const pbs2=others(store);
 expect(saveGhost(store,A2,A2)).toBe(true);expect(orderOf(store.getItem(ghostKey(A2)))).toBe(3);
 expect(saveGhost(store,C,C)).toBe(true);
 expect(store.getItem(ghostKey(B))).toBeNull();expect(loadGhost(store,A2)).toEqual(A2);expect(loadGhost(store,C)).toEqual(C);
 expect(ghostTotal(store)).toBeLessThanOrEqual(BUDGET);expect(others(store)).toBe(pbs2);expect(pbs).not.toBe(pbs2);expect(foreign).not.toBe('');
 for(const k of ['glimmertown-lab-save','glimmertown-lab-save_bak','defendtaipei-progress-v1','physical-fpv-settings-v1','physical-fpv-ui-lang-v1'])expect(store.map.has(k)).toBe(true);
});

it('G15 U4 dead entries go first in key order, removal stops once the total fits, and a failed removal keeps the new Ghost',()=>{
 const fast=ghostOf(fixture()),store=origin();
 const L=asClass(fast,'light','standard'),N=asClass(fast,'trainer','endurance'),Z=asClass(fast,'light','endurance'),X=asClass(fast,'light','standard','torque');
 for(const g of [L,N,Z,X])savePB(store,g);
 expect(saveGhost(store,L,L)).toBe(true);expect(saveGhost(store,Z,Z)).toBe(true);
 // Z becomes stale: its class PB is replaced by a different, faster race.
 const zPB={total:Z.total-1,splits:Z.splits.map((s,i)=>({...s,elapsed:i?s.elapsed-1/ (Z.splits.length-1)*i:0,sector:i?s.sector-1/(Z.splits.length-1):0}))};
 expect(saveRecord(store,Z.physicsModel,Z.assembly,zPB,Z.courseVersion)).not.toBeNull();expect(loadGhost(store,Z)).toBeNull();
 const misfiled=PREFIX+'a-misfiled',junk=PREFIX+'b-junk',late=PREFIX+'zz-junk',big=PREFIX+'c-order-too-big';
 store.map.set(misfiled,JSON.stringify({order:1,...X}));store.map.set(junk,'not json');store.map.set(big,'{"order":1e300,"schema":"physical-fpv-pb-ghost-v1"}');store.map.set(late,'{"order":2,"schema":"other"}');
 const keep=others(store);
 expect(saveGhost(store,N,N)).toBe(true);
 // Removal order: a-misfiled, b-junk, c-order-too-big, then the stale class key (it sorts before zz-junk), and it stops there.
 expect(store.getItem(misfiled)).toBeNull();expect(store.getItem(junk)).toBeNull();expect(store.getItem(big)).toBeNull();
 expect(store.getItem(ghostKey(Z))).toBeNull();expect(store.getItem(late)).not.toBeNull();
 expect(loadGhost(store,L)).toEqual(L);expect(loadGhost(store,N)).toEqual(N);expect(ghostTotal(store)).toBeLessThanOrEqual(BUDGET);expect(others(store)).toBe(keep);
 // A removeItem that throws: the new Ghost stays and saveGhost still reports success.
 const stuck={getItem:store.getItem,setItem:store.setItem,key:store.key,get length(){return store.map.size;},removeItem:()=>{throw Error('locked');}};const total=ghostTotal(store);
 expect(saveGhost(stuck,X,X)).toBe(true);expect(loadGhost(store,X)).toEqual(X);expect(ghostTotal(store)).toBeGreaterThan(total);
});

it('G15 U5 a failed write removes nothing',()=>{
 const slow=ghostOf(fixture('british-slalom',2.3)),fast=ghostOf(fixture());
 const A=asClass(slow,'light','standard'),B=asClass(slow,'trainer','endurance'),C=asClass(slow,'light','endurance');
 for(const fill of [false,true]){
  const store=origin(fill?QUOTA:Infinity);for(const g of [A,B,C])savePB(store,g);expect(saveGhost(store,A,A)).toBe(true);expect(saveGhost(store,B,B)).toBe(true);
  const C2=asClass(fast,'light','endurance');savePB(store,C2);expect(saveGhost(store,C,C)).toBe(false);
  // Throwing setItem: the class's old, slower Ghost is there for the faster lap to replace, and stays.
  // Full quota: the class has no Ghost yet and 10 code units are free; removing A or B would make room, but nothing goes.
  if(!fill)store.map.set(ghostKey(C2),JSON.stringify({order:9,...C}));
  else store.map.set('glimmertown-lab-big','z'.repeat(QUOTA-[...store.map].reduce((n,[k,v])=>n+k.length+v.length,0)-'glimmertown-lab-big'.length-10));
  const before=JSON.stringify([...store.map]);
  const target=fill?store:{...store,setItem:()=>{throw new DOMException('quota','QuotaExceededError');}};
  expect(saveGhost(target,C2,C2)).toBe(false);expect(JSON.stringify([...store.map])).toBe(before);
 }
});

function scaled(g:GhostRecord,k:number):GhostRecord{
 const startedAt=.001,total=g.total*k,finishedAt=startedAt+total,sourceTicks=Math.ceil(finishedAt/FIXED_DT);
 const poses=[];for(let t=0;t<=sourceTicks;t+=4)poses.push({...g.poses[(t/4)%g.poses.length],tick:t});if(poses.at(-1)!.tick!==sourceTicks)poses.push({...g.poses[0],tick:sourceTicks});
 return {...g,startedAt,finishedAt,total,sourceTicks,splits:g.splits.map(s=>({...s,elapsed:s.elapsed*k,sector:s.sector*k})),poses};
}
it('G15 U6 a valid Ghost between 2 and 4 MiB is refused without writes or removals',()=>{
 const fast=ghostOf(fixture()),store=origin();const other=asClass(fast,'light','standard');savePB(store,other);expect(saveGhost(store,other,other)).toBe(true);
 const big=scaled(fast,3.2),bytes=entryBytes(ghostKey(big),JSON.stringify({order:2,...big}));expect(bytes).toBeGreaterThan(BUDGET);expect(bytes).toBeLessThan(4*1024*1024);
 savePB(store,big);const before=JSON.stringify([...store.map]);expect(saveGhost(store,big,big)).toBe(false);expect(JSON.stringify([...store.map])).toBe(before);
 const twin=scaled(fast,1.2),twinStore=origin();savePB(twinStore,twin);expect(saveGhost(twinStore,twin,twin)).toBe(true);expect(loadGhost(twinStore,twin)).toEqual(twin);
});

it('G15 U7 each entry starts with its write order, and loadGhost returns the record without it',()=>{
 const slow=ghostOf(fixture('british-slalom',2.3)),fast=ghostOf(fixture()),store=origin();
 const A=asClass(slow,'light','standard'),B=asClass(slow,'trainer','endurance');for(const g of [A,B])savePB(store,g);
 expect(saveGhost(store,A,A)).toBe(true);expect(store.getItem(ghostKey(A))!.startsWith('{"order":1,')).toBe(true);
 expect(saveGhost(store,B,B)).toBe(true);expect(orderOf(store.getItem(ghostKey(B)))).toBe(2);
 const A2=asClass(fast,'light','standard');savePB(store,A2);expect(saveGhost(store,A2,A2)).toBe(true);expect(orderOf(store.getItem(ghostKey(A2)))).toBe(3);
 const loaded=loadGhost(store,A2)!;expect(loaded).toEqual(A2);expect(Object.keys(loaded)).not.toContain('order');
 const legacy=origin();savePB(legacy,A);legacy.map.set(ghostKey(A),JSON.stringify(A));expect(loadGhost(legacy,A)).toBeNull();
 legacy.map.set(ghostKey(A),JSON.stringify({order:7,...A}));expect(loadGhost(legacy,A)).toEqual(A);
 expect(recordKey(A.physicsModel,A.assembly,A.courseVersion)).toContain('light');
});
