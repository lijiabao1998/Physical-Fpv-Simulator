import {beforeAll,it,expect} from 'vitest';
import {COURSES,getCourse,gateBoxes} from '../src/game/courses';
import {GATES,FIELD_BOXES} from '../src/game/field';
import {Course} from '../src/game/course';
import {add,rotate,scale} from '../src/physics/math';
import {GameSession} from '../src/game/session';
import {G07_MODEL,G08_MODEL} from '../src/physics/transient';
import {DEFAULT_ASSEMBLY,FIXED_DT} from '../src/physics/config';
import {recordKey} from '../src/game/records';
import {FlightWorld,initPhysics} from '../src/physics/world';
import {ZERO} from '../src/physics/controller';
beforeAll(initPhysics);
it('G10 keeps Training geometry and record identity exactly; course IDs/versions reject unknown',()=>{
 const c=getCourse();expect(c.boxes).toBe(FIELD_BOXES);expect(c.gates.map(({rotation,...g})=>g)).toEqual(GATES);
 expect(recordKey(G08_MODEL,DEFAULT_ASSEMBLY)).toBe('physical-fpv-race-v1:training-five-v1:g08-transient-v1:trainer:standard:balanced:5inch');expect(()=>getCourse('missing')).toThrow();expect(()=>getCourse(c.id,'missing')).toThrow();
});
it('G10 British Slalom really turns backwards in X, climbs and descends, scoring only ordered planes',()=>{
 const d=getCourse('british-slalom'),c=new Course(true,d.id);expect(d.gates.some((g,i)=>i>0&&g.center[0]<d.gates[i-1].center[0])).toBe(true);expect(Math.max(...d.gates.map(g=>g.center[2]))-Math.min(...d.gates.map(g=>g.center[2]))).toBeGreaterThan(5);
 d.gates.forEach((g,i)=>{const n=rotate(g.rotation,[1,0,0]),a=add(g.center,scale(n,-1)),b=add(g.center,n);expect(c.update(b,a,i+1,.02)).toBe(false);expect(c.update(a,b,i+1,.02)).toBe(true);expect(c.update(a,b,i+1.1,.02)).toBe(false);});expect(c.next).toBe(d.gates.length);expect(c.finishedAt).not.toBeNull();
});
it('G10 visible shared oriented boxes exactly match static Rapier translation, size and orientation',()=>{
 const d=getCourse('british-slalom'),w=new FlightWorld(undefined,true,d.id);const boxes=gateBoxes(d.gates);expect(boxes).toEqual(d.boxes.slice(0,boxes.length));
 const colliders:any[]=[];w.world.forEachCollider(c=>{if(c.handle!==w.collider.handle)colliders.push(c);});
 boxes.forEach((b,i)=>{const c=colliders[i+1];const p=c.translation(),h=c.halfExtents(),q=c.rotation();[p.x,p.y,p.z].forEach((x,k)=>expect(x).toBeCloseTo(b.center[k],5));[h.x,h.y,h.z].forEach((x,k)=>expect(x).toBeCloseTo(b.half[k],6));[q.w,q.x,q.y,q.z].forEach((x,k)=>expect(x).toBeCloseTo(b.rotation![k],6));});w.dispose();
});
it('G10 switching resets/disarms and old replay stays Training; both physics models replay unchanged',()=>{
 for(const model of [G07_MODEL,G08_MODEL]){const s=new GameSession(undefined,true,model);s.start();s.arm(0);s.switchCourse('british-slalom');expect(s.armed).toBe(false);expect(s.time).toBe(0);expect(s.course.splits).toEqual([]);s.arm(0);for(let i=0;i<240;i++)s.step({...ZERO,throttle:.6,roll:.05,pitch:-.1});const end=s.snapshot(),b=s.exportReplay('same');s.replay(b);for(let i=0;i<b.events.length;i++)s.step(ZERO,FIXED_DT);expect(s.world.position).toEqual(end.position);expect(s.course.splits).toEqual(end.splits);expect(s.courseId).toBe('british-slalom');const legacy={...b,courseId:undefined,courseVersion:undefined};s.replay(legacy);expect(s.courseId).toBe('training-straight');expect(()=>s.replay({...b,courseVersion:'unknown'})).toThrow();s.world.dispose();}
});
it('G10 each course has a unique record namespace, separate from historical Training',()=>{
 const keys=COURSES.map(c=>recordKey(G08_MODEL,DEFAULT_ASSEMBLY,c.version));expect(new Set(keys).size).toBe(COURSES.length);expect(keys[1]).not.toBe(keys[0]);
});
it('G10 real fixed-input takeoff scores British Gate 1 and replays its timestamp without body writes',()=>{
 const s=new GameSession(undefined,true,G08_MODEL,'british-slalom');s.start();s.arm(0);
 for(let i=0;i<1440&&s.state==='flying';i++)s.step({...ZERO,throttle:i<180?.56:.38,pitch:i<180?0:.6});
 expect(s.course.next).toBe(1);expect(s.state).toBe('crashed');const end=s.snapshot(),start=s.course.startedAt,b=s.exportReplay('same');
 s.replay(b);for(let i=0;i<b.events.length;i++)s.step(ZERO);expect(s.world.position).toEqual(end.position);expect(s.course.splits).toEqual(end.splits);expect(s.course.startedAt).toBe(start);expect(s.state).toBe('crashed');s.world.dispose();
});
