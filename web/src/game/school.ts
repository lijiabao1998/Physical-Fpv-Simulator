import {FIXED_DT} from '../physics/config';
import type {Controls} from '../physics/controller';

/** Read-only native observations. No reference to GameSession or mutable world is kept. */
export interface SchoolObservation {
  time:number; state:string; armed:boolean; position:readonly number[];
  velocity:readonly number[]; quaternion:readonly number[]; rates:readonly number[];
  controls:Readonly<Controls>; contact:boolean; practice:boolean;
  courseId:string; courseVersion:string; physicsModel:string;
  assemblyKey:string; courseValid:boolean; gate:number; gateCount:number;
  splits:readonly {gate:number;elapsed:number;sector:number}[];
}
export type SchoolLesson='takeoff'|'hover'|'axes'|'gate'|'challenge'|'complete';
export const SCHOOL_TEST_LIMITS=Object.freeze({takeoffHeight:.75,hoverMin:1,hoverMax:3,
  hoverRadius:4,horizontalSpeed:.75,verticalSpeed:.5,tiltDegrees:20,hoverTicks:720,
  axisTicks:60,axisCommand:.15,axisRate:.05});
const AXES=['throttle','pitch','roll','yaw'] as const;
const identity=(o:SchoolObservation)=>JSON.stringify([o.courseId,o.courseVersion,o.physicsModel,o.assemblyKey]);
const finite=(a:readonly number[],n:number)=>a.length===n&&a.every(Number.isFinite);
export class FlightSchool {
  private token:object|null=null;private key='';private lastTime=0;private origin=[0,0];
  private armedSeen=false;private zeroSeen=false;private gentleSeen=false;private lifted=false;
  private hoverTicks=0;private axisTicks=0;private axisIndex=0;private gateStart=0;
  private replayLocked=false;private invalid=false;
  active=false;lesson:SchoolLesson='takeoff';feedback='School ready';
  begin(attempt:object,o:SchoolObservation){this.clear();this.active=true;this.token=attempt;this.key=identity(o);this.lastTime=o.time;this.origin=[o.position[0],o.position[1]];this.observe(attempt,o);}
  stop(){this.clear();this.active=false;this.token=null;this.feedback='School closed';}
  private clear(){this.lesson='takeoff';this.zeroSeen=false;this.armedSeen=false;this.gentleSeen=false;this.lifted=false;this.hoverTicks=0;this.axisTicks=0;this.axisIndex=0;this.gateStart=0;this.replayLocked=false;this.invalid=false;this.feedback='Zero throttle, then hold ARM';}
  markReplay(){if(!this.active)return;this.clear();this.replayLocked=true;this.feedback='Replay cannot earn school progress';}
  private reject(){this.clear();this.invalid=true;this.feedback='Attempt invalid. Retry school';}
  snapshot(){return {active:this.active,lesson:this.lesson,completed:['takeoff','hover','axes','gate','challenge','complete'].indexOf(this.lesson),feedback:this.feedback,
    takeoffStep:!this.zeroSeen?'zero':!this.armedSeen?'arm':!this.lifted?'lift':'disarm',hoverSeconds:this.hoverTicks*FIXED_DT,
    hoverRequiredSeconds:SCHOOL_TEST_LIMITS.hoverTicks*FIXED_DT,axis:AXES[this.axisIndex]??null,axisSeconds:this.axisTicks*FIXED_DT,
    blocked:this.invalid||this.replayLocked,provisionalDifficulty:true};}
  observe(attempt:object,o:SchoolObservation){
    if(!this.active)return;
    if(this.token!==attempt||this.key!==identity(o)){if(this.replayLocked){this.token=attempt;this.key=identity(o);return;}this.begin(attempt,o);return;}
    if(o.state==='replay'){this.markReplay();return;}
    if(this.replayLocked||this.invalid)return;
    if(o.state==='crashed'||!o.courseValid){this.reject();return;}
    if(!Number.isFinite(o.time)||!finite(o.position,3)||!finite(o.velocity,3)||!finite(o.quaternion,4)||!finite(o.rates,3)||!Object.values(o.controls).every(Number.isFinite)){this.reject();return;}
    const elapsed=o.time-this.lastTime;this.lastTime=o.time;
    if(elapsed< -1e-8){this.begin(attempt,o);return;}
    if(o.state==='paused'||o.state==='ready'){if(this.lesson==='takeoff'){this.zeroSeen=false;this.armedSeen=false;this.gentleSeen=false;this.lifted=false;this.feedback='Safety stop. Restart safe takeoff';}return;}
    const tick=Math.abs(elapsed-FIXED_DT)<1e-7;
    if(elapsed>FIXED_DT+1e-7){this.hoverTicks=0;this.axisTicks=0;this.feedback='Observe every fixed physics tick';return;}
    if(this.lesson==='complete')return;
    if(this.lesson==='takeoff'){
      if(o.state!=='flying')return;
      if(!o.armed&&o.controls.throttle>=0&&o.controls.throttle<=.025&&!this.armedSeen)this.zeroSeen=true;
      if(o.armed&&!this.armedSeen&&this.zeroSeen&&o.controls.throttle>=0&&o.controls.throttle<=.025)this.armedSeen=true;
      if(o.armed&&this.armedSeen&&o.controls.throttle>.025&&o.controls.throttle<=.35)this.gentleSeen=true;
      if(tick&&o.armed&&this.gentleSeen&&!o.contact&&o.position[2]>=SCHOOL_TEST_LIMITS.takeoffHeight)this.lifted=true;
      this.feedback=!this.zeroSeen?'Zero throttle, then hold ARM':!this.armedSeen?'Hold ARM with zero throttle':!this.lifted?'Raise throttle gently to take off':'Disarm safely to finish takeoff lesson';
      if(this.lifted&&!o.armed){this.lesson='hover';this.feedback='Rearm and hold a stable hover';}return;
    }
    if(this.lesson==='hover'){
      if(!tick)return;
      const q=o.quaternion;const up=1-2*(q[1]*q[1]+q[2]*q[2]);
      const stable=o.state==='flying'&&o.armed&&!o.contact&&o.position[2]>=1&&o.position[2]<=3&&
        Math.hypot(o.position[0]-this.origin[0],o.position[1]-this.origin[1])<=4&&Math.hypot(o.velocity[0],o.velocity[1])<=.75&&Math.abs(o.velocity[2])<=.5&&up>=Math.cos(20*Math.PI/180);
      this.hoverTicks=stable?this.hoverTicks+1:0;this.feedback=stable?'Hold this stable hover':'Return to the hover zone';
      if(this.hoverTicks>=720){this.lesson='axes';this.feedback='Practice throttle';}return;
    }
    if(this.lesson==='axes'){
      if(!tick)return;
      const axis=AXES[this.axisIndex];const response=axis==='throttle'?o.velocity[2]>.15:Math.abs(o.rates[axis==='roll'?0:axis==='pitch'?1:2])>.05;
      const valid=o.state==='flying'&&o.armed&&!o.contact&&Math.abs(o.controls[axis])>.15&&response;
      this.axisTicks=valid?this.axisTicks+1:0;this.feedback=`Practice ${axis}`;
      if(this.axisTicks>=60){this.axisTicks=0;this.axisIndex++;if(this.axisIndex===4){this.lesson='gate';this.gateStart=o.gate;this.feedback='Fly through the next gate in order';}}
      return;
    }
    const ordered=o.practice&&Number.isInteger(o.gate)&&o.gateCount>0&&o.gate===o.splits.length&&o.splits.every((s,i)=>s.gate===i+1&&Number.isFinite(s.elapsed)&&s.elapsed>=0&&Number.isFinite(s.sector)&&s.sector>=0);
    if(this.lesson==='gate'&&ordered&&o.gate>this.gateStart){this.lesson='challenge';this.feedback='Complete the course with valid ordered gates';}
    if(this.lesson==='challenge'&&ordered&&o.state==='finished'&&o.gate===o.gateCount){this.lesson='complete';this.feedback='School complete. Simulation training only';}
  }
}
