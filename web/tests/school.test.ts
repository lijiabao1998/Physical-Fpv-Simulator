import {mkdirSync,writeFileSync} from 'node:fs';
import {beforeAll,it,expect} from 'vitest';
import {FlightSchool,type SchoolObservation} from '../src/game/school';
import {FIXED_DT} from '../src/physics/config';
import {ZERO} from '../src/physics/controller';
import {GameSession} from '../src/game/session';
import {initPhysics} from '../src/physics/world';
import {getCourse} from '../src/game/courses';
beforeAll(initPhysics);
const observation=():SchoolObservation=>({time:0,state:'flying',armed:false,position:[0,0,.105],velocity:[0,0,0],quaternion:[1,0,0,0],rates:[0,0,0],controls:{...ZERO},contact:false,practice:true,courseId:'training-straight',courseVersion:'training-five-v1',physicsModel:'g08-transient-v1',assemblyKey:'trainer:standard:balanced:5inch',courseValid:true,gate:0,gateCount:5,splits:[]});
function rig(){const o=observation(),s=new FlightSchool(),token={};s.begin(token,o);const tick=(change:Partial<SchoolObservation>={},n=1)=>{Object.assign(o,change);for(let i=0;i<n;i++){o.time+=FIXED_DT;s.observe(token,o);}};return {o,s,token,tick};}
function takeoff(r:ReturnType<typeof rig>){r.tick({armed:true});r.tick({controls:{...ZERO,throttle:.25}});r.tick({controls:{...ZERO,throttle:.6},position:[0,0,1.5]});r.tick({armed:false,controls:{...ZERO}});expect(r.s.lesson).toBe('hover');}
function axes(r:ReturnType<typeof rig>){takeoff(r);r.tick({armed:true,position:[0,0,2],controls:{...ZERO,throttle:.5}},720);expect(r.s.lesson).toBe('axes');for(const axis of ['throttle','pitch','roll','yaw'] as const)r.tick({controls:{...ZERO,[axis]:.4},velocity:[0,0,.2],rates:[.1,.1,.1]},60);expect(r.s.lesson).toBe('gate');}
it('requires observed zero ARM, gentle raise, native altitude, then deliberate disarm',()=>{const r=rig();r.tick({position:[0,0,2]},1000);expect(r.s.lesson).toBe('takeoff');r.tick({armed:true,controls:{...ZERO,throttle:.9}},10);expect(r.s.snapshot().takeoffStep).toBe('arm');const q=rig();takeoff(q);});
it('pause or crash never counts as takeoff disarm',()=>{const r=rig();r.tick({armed:true});r.tick({controls:{...ZERO,throttle:.2}});r.tick({position:[0,0,2]});r.tick({state:'paused',armed:false},1000);expect(r.s.lesson).toBe('takeoff');r.tick({state:'flying',armed:false});expect(r.s.lesson).toBe('takeoff');r.tick({state:'crashed'});expect(r.s.snapshot().blocked).toBe(true);expect(r.s.snapshot().completed).toBe(0);});
it('hover requires consecutive native fixed ticks; low height, contact, speed, tilt and time gaps fail',()=>{for(const bad of [{position:[0,0,.9]},{position:[5,0,2]},{velocity:[1,0,0]},{velocity:[0,0,.6]},{contact:true},{quaternion:[Math.cos(.3),Math.sin(.3),0,0]}]){const r=rig();takeoff(r);r.tick({armed:true,position:[0,0,2]},719);expect(r.s.lesson).toBe('hover');r.tick(bad);expect(r.s.snapshot().hoverSeconds).toBe(0);}const r=rig();takeoff(r);r.tick({armed:true,position:[0,0,2]},10);r.o.time+=3;r.s.observe(r.token,r.o);expect(r.s.snapshot().hoverSeconds).toBe(0);});
it('paused observations do not advance hover, repeated timestamp does not advance',()=>{const r=rig();takeoff(r);r.tick({armed:true,position:[0,0,2]},100);const seconds=r.s.snapshot().hoverSeconds;r.tick({state:'paused'},1000);expect(r.s.snapshot().hoverSeconds).toBe(seconds);r.o.state='flying';for(let i=0;i<1000;i++)r.s.observe(r.token,r.o);expect(r.s.snapshot().hoverSeconds).toBe(seconds);});
it('axes require native response, not commands alone',()=>{const r=rig();takeoff(r);r.tick({armed:true,position:[0,0,2]},720);r.tick({controls:{...ZERO,throttle:.8}},1000);expect(r.s.snapshot().axis).toBe('throttle');r.tick({velocity:[0,0,.2]},60);expect(r.s.snapshot().axis).toBe('pitch');});
it('complete ordered flow; invalid, reversed or repeated gates cannot pass',()=>{const r=rig();axes(r);r.tick({},20);expect(r.s.lesson).toBe('gate');r.tick({gate:1,splits:[{gate:2,elapsed:0,sector:0}]});expect(r.s.lesson).toBe('gate');r.tick({gate:1,splits:[{gate:1,elapsed:0,sector:0}]});expect(r.s.lesson).toBe('challenge');r.tick({state:'finished',gate:4,splits:Array.from({length:4},(_,i)=>({gate:i+1,elapsed:i,sector:i?1:0}))});expect(r.s.lesson).toBe('challenge');r.tick({gate:5,splits:Array.from({length:5},(_,i)=>({gate:i+1,elapsed:i,sector:i?1:0}))});expect(r.s.lesson).toBe('complete');});
it('attempt, configuration, crash and exit clear progress; no storage or language state',()=>{for(const mode of ['attempt','assembly','crash','exit']){const r=rig();axes(r);if(mode==='attempt')r.s.observe({},r.o);if(mode==='assembly'){r.o.assemblyKey='different';r.s.observe(r.token,r.o);}if(mode==='crash')r.tick({state:'crashed'});if(mode==='exit')r.s.stop();expect(r.s.snapshot().completed).toBe(0);}});
it('replay remains blocked across pause/resume and token change until explicit fresh begin',()=>{const r=rig();r.s.markReplay();r.o.state='replay';r.s.observe({},r.o);r.o.state='paused';r.s.observe(r.token,r.o);r.o.state='flying';r.s.observe(r.token,r.o);expect(r.s.snapshot().blocked).toBe(true);r.s.begin({},observation());expect(r.s.snapshot().blocked).toBe(false);});
it('nonfinite data fails closed; observer never mutates deeply frozen observation',()=>{const r=rig();const frozen=structuredClone(r.o);for(const v of Object.values(frozen))if(typeof v==='object'&&v)Object.freeze(v);Object.freeze(frozen);expect(()=>r.s.observe(r.token,frozen)).not.toThrow();r.tick({velocity:[NaN,0,0]});expect(r.s.snapshot().blocked).toBe(true);});
it('native ARM rejection and exact physics/replay/energy noninterference across 960 steps',()=>{const a=new GameSession(),b=new GameSession();a.start();b.start();expect(a.arm(.8)).toBe(false);expect(b.arm(.8)).toBe(false);const school=new FlightSchool();const obs=(g:GameSession):SchoolObservation=>({...g.snapshot(),assemblyKey:JSON.stringify(g.assembly),practice:g.practice,gateCount:getCourse(g.courseId).gates.length,contact:g.world.contact,controls:g.lastControls});school.begin(a.course,obs(a));a.arm(0);b.arm(0);school.observe(a.course,obs(a));for(let i=0;i<960;i++){const c={...ZERO,throttle:Math.min(.55,i/600)};a.step(c);b.step(c);school.observe(a.course,obs(a));expect(a.snapshot()).toEqual(b.snapshot());}expect(a.exportReplay('same')).toEqual(b.exportReplay('same'));a.world.dispose();b.world.dispose();});
it('ordinary native controls complete all five lessons without state placement or physics writes',()=>{
 const game=new GameSession();game.start();const school=new FlightSchool();
 const observation=():SchoolObservation=>({...game.snapshot(),controls:game.lastControls,contact:game.world.contact,practice:game.practice,assemblyKey:JSON.stringify(game.assembly),gateCount:getCourse(game.courseId).gates.length});
 school.begin(game.course,observation());expect(game.arm(0)).toBe(true);school.observe(game.course,observation());
 const step=(c:typeof ZERO)=>{game.step(c);school.observe(game.course,observation());};step({...ZERO,throttle:.2});
 const clamp=(x:number,a:number,b:number)=>Math.max(a,Math.min(b,x));
 // Test-only ordinary input controller, like G10's existing navigation test. Never ships in player.
 const control=(target:number[])=>{const p=game.world.position,v=game.world.velocity,[w,x,y,z]=game.world.quaternion;
 const roll=Math.atan2(2*(w*x+y*z),1-2*(x*x+y*y)),pitch=Math.asin(clamp(2*(w*y-z*x),-1,1)),yaw=Math.atan2(2*(w*z+x*y),1-2*(y*y+z*z));
 const a=target.map((t,k)=>clamp(1.3*(t-p[k])-2*v[k],-3,3));const ax=Math.cos(yaw)*a[0]+Math.sin(yaw)*a[1],ay=-Math.sin(yaw)*a[0]+Math.cos(yaw)*a[1];
 return {throttle:clamp(game.power.hover()*Math.sqrt((9.80665+a[2])/(9.80665*Math.max(.4,Math.cos(roll)*Math.cos(pitch)))),.05,.8),pitch:clamp(Math.atan2(ax,9.80665+a[2])/.6,-1,1),roll:clamp(-Math.atan2(ay,9.80665+a[2])/.6,-1,1),yaw:clamp(-yaw*.8,-.4,.4)};};
 let disarmed=false;const stageTicks:Record<string,number>={};const commands:unknown[]=[];const transitions:unknown[]=[];let lastLesson=school.lesson;
 for(let tick=0;tick<240*100&&school.lesson!=='complete'&&game.state==='flying';tick++){
   const stage=school.snapshot();stageTicks[stage.lesson]=(stageTicks[stage.lesson]??0)+1;
   if(stage.lesson==='takeoff'&&stage.takeoffStep==='disarm'&&!disarmed){game.disarm();school.observe(game.course,observation());disarmed=true;expect(game.arm(0)).toBe(true);school.observe(game.course,observation());}
   let c=control([0,0,2]);
   if(school.lesson==='axes'){
     const axis=school.snapshot().axis;if(axis==='throttle')c=control([0,0,3]);else if(axis)c={...c,[axis]:.3};
   }
   if(school.lesson==='gate'||school.lesson==='challenge'){const gate=getCourse(game.courseId).gates[game.course.next];if(gate)c=control([gate.center[0]+2,gate.center[1],gate.center[2]]);}
   commands.push({tick,controls:c,school:school.lesson});step(c);if(lastLesson!==school.lesson){transitions.push({tick,from:lastLesson,to:school.lesson,snapshot:game.snapshot()});lastLesson=school.lesson;}
 }
 expect({lesson:school.lesson,state:game.state,progress:school.snapshot(),stageTicks}).toMatchObject({lesson:'complete',state:'finished'});
 expect(game.course.next).toBe(5);expect(game.course.invalid).toBe(false);mkdirSync('numerical-results',{recursive:true});writeFileSync('numerical-results/g12-school-flight.json',JSON.stringify({scope:'Test-only normal native control inputs. No position/force writes or player autopilot. Not human or hardware validation. Difficulty provisional.',stageTicks,transitions,commands,result:game.snapshot(),school:school.snapshot()},null,2));game.world.dispose();
},30000);
