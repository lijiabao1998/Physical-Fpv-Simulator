// Re-apply G11's main.ts and i18n.ts edits (02b2455..e0c6d87) onto a newer base file.
// usage: node apply-g11.mjs main <base main.ts> <G11 main.ts> <out> [--school-tick]
//        node apply-g11.mjs i18n <base i18n.ts> <G11 i18n.ts> <out>
// Every anchor must occur exactly once in the base file, otherwise the script aborts.
import {readFileSync,writeFileSync} from 'node:fs';
const [kind,basePath,g11Path,out,...flags]=process.argv.slice(2);
let src=readFileSync(basePath,'utf8');const g11=readFileSync(g11Path,'utf8');const g11Lines=g11.split('\n');
const log=[];
function once(hay,needle,label){const i=hay.indexOf(needle);if(i<0)throw Error(`${label}: anchor not found`);if(hay.indexOf(needle,i+1)>=0)throw Error(`${label}: anchor not unique`);return i;}
function replace(label,oldStr,newStr){once(src,oldStr,label);src=src.replace(oldStr,()=>newStr);log.push(label);}
function g11Line(prefix,label){const hits=g11Lines.filter(l=>l.startsWith(prefix));if(hits.length!==1)throw Error(`${label}: G11 line ${JSON.stringify(prefix)} found ${hits.length}x`);return hits[0];}
if(kind==='main'){
 // 1. ghost import, next to the course import (G11 main.ts line 10)
 const imp=g11Line('import {GhostPlayback,','import');
 replace('1 import',"import {COURSES,getCourse,type CourseId} from './game/courses';\n","import {COURSES,getCourse,type CourseId} from './game/courses';\n"+imp+'\n');
 // 2. HUD nodes inside the course card, before the legacy line (school-open stays last, G13 grid relies on it)
 replace('2 markup','<small id="race-splits"></small><small id="legacy-best"></small>','<small id="race-splits"></small><button id="ghost-toggle" aria-pressed="true">PB Ghost: ON</button><small id="ghost-status"></small><div id="ghost-splits" aria-label="Gate split comparison"></div><small id="legacy-best"></small>');
 // 3. ghost state + observeGhost + visibleGhost (G11 lines 45-47)
 const state=[g11Line('const ghostRecorder=new GhostRecorder()','3a'),g11Line('function observeGhost(){','3b'),g11Line('function visibleGhost(){','3c')].join('\n');
 replace('3 state',"let bestSavedFor:GameSession['course']|null=null;\n","let bestSavedFor:GameSession['course']|null=null;\n"+state+'\n');
 // 4. updateHud observes the recorder too (after main's school observer)
 replace('4 updateHud','function updateHud(){observeSchool();updateSchoolHud();const s=game.snapshot();','function updateHud(){observeSchool();updateSchoolHud();observeGhost();const s=game.snapshot();');
 // 5. three HUD lines after race-class (G11 lines 119-121)
 const hud=[g11Line(" text('ghost-toggle',",'5a'),g11Line(" text('ghost-status',",'5b'),g11Line(' const comparisons=gateComparisons(','5c')].join('\n');
 const raceClass=src.split('\n').find(l=>l.startsWith(" text('race-class',"));
 replace('5 hud lines',raceClass+'\n',raceClass+'\n'+hud+'\n');
 // 6. PB save guard (recordable, valid, finished) + Ghost save after a successful PB write
 replace('6 save','if(game.course.finishedAt!==null&&bestSavedFor!==game.course){bestSavedFor=game.course;try{const result=saveRecord(localStorage,game.physicsModel,game.assembly,{total:s.courseTime,splits:s.splits},getCourse(game.courseId).version);if(result!==null)best=result.total;}catch{}}',
  "if(game.recordable&&!game.course.invalid&&game.state==='finished'&&game.course.finishedAt!==null&&bestSavedFor!==game.course){bestSavedFor=game.course;try{const result=saveRecord(localStorage,game.physicsModel,game.assembly,{total:s.courseTime,splits:s.splits},getCourse(game.courseId).version);if(result!==null){best=result.total;const candidate=ghostRecorder.completed(game,__BUILD_SHA__);if(candidate)saveGhost(localStorage,ghostClass(game),candidate);}}catch{}}");
 // 7. animate observes before stepping
 replace('7 animate',' const physicsStart=performanceStats.enabled?performance.now():0;',' observeGhost();const physicsStart=performanceStats.enabled?performance.now():0;');
 // 8. every fixed tick of the frame loop feeds both observers
 replace('8 step loop','for(let step=0;step<plan.steps;step++){game.step(frame.controls);observeSchool();}','for(let step=0;step<plan.steps;step++){game.step(frame.controls);observeSchool();ghostRecorder.observe(game);}');
 // 9. render the visual-only pose
 replace('9 render','scene.render(game,dt);','scene.render(game,dt,visibleGhost());');
 // 10. native toggle handler, after main's school handlers
 replace('10 toggle',"el<HTMLSelectElement>('course-select').onchange=()=>{input.clear();","el('ghost-toggle').onclick=()=>{ghostEnabled=!ghostEnabled;updateHud();};el<HTMLSelectElement>('course-select').onchange=()=>{input.clear();");
 // 11. dev-only fixture hooks (copied verbatim from G11)
 const hooks=/localInputFlight:\(controls:Controls\[\],count=controls\.length\)=>\{.*?\},ghost:\(\)=>\(\{.*?recordable:game\.recordable\}\),/.exec(g11)[0];
 replace('11 hooks','snapshot:()=>({...game.snapshot(),camera:scene.cameraMode,frame}),',hooks+'snapshot:()=>({...game.snapshot(),camera:scene.cameraMode,frame}),');
 // 12. tick hook feeds both observers
 replace('12 tick',"throw Error('Invalid test tick count');for(let i=0;i<count;i++){game.step(controls);observeSchool();}updateHud();}","throw Error('Invalid test tick count');observeGhost();for(let i=0;i<count;i++){game.step(controls);observeSchool();ghostRecorder.observe(game);}updateHud();}");
 // 13. optional (port decision): G12's schoolTick hook steps the game too
 if(flags.includes('--school-tick'))replace('13 schoolTick','schoolTick:(controls:Controls)=>{game.step(controls);observeSchool();}','schoolTick:(controls:Controls)=>{game.step(controls);observeSchool();ghostRecorder.observe(game);}');
}else if(kind==='i18n'){
 // G11 dictionary lines go after G12's last dictionary line; G11's rule after G12's Lessons rule.
 const dict=['PB Ghost: ON|','PB Ghost: OFF|','Replay preview · PB protected|','No matching Ghost for this configuration|','Gate split comparison|','Gate|','You|','PB|'].map(p=>g11Line(p,'dict '+p));
 const lastG12='Mode 2: left stick throttle/yaw · right stick roll/pitch · hold A/✕ 0.6s ARM · B/○ disarm|';
 const anchor=src.split('\n').find(l=>l.startsWith(lastG12));
 replace('i18n dictionary',anchor+'\n',anchor+'\n'+dict.join('\n')+'\n');
 const rule=g11Line(' [/^PB (.+) s · (waiting at Gate 1|chase your best|hidden)$/','rule');
 const lessons=src.split('\n').find(l=>l.startsWith(' [/^Lessons (\\d+) \\/ 5 · Hover'));
 replace('i18n rule',lessons+'\n',lessons+'\n'+rule+'\n');
}else throw Error('kind must be main or i18n');
writeFileSync(out,src);console.log(JSON.stringify({kind,out,applied:log}));
