import { GATES } from './field';
import {getCourse,type CourseId} from './courses';
import {intersectGate} from './gate-geometry';
import type { V3,Q4 } from '../physics/math';
export const COURSE_VERSION='training-five-v1';
export interface GateSplit {gate:number;elapsed:number;sector:number}
/** Ordered forward plane crossings. Interpolate at plane, then test the clear aperture. */
export class Course {
  splits:GateSplit[]=[];invalid=false;
  invalidate(){this.invalid=true;this.finishedAt=null;}
  next=0; startedAt:number|null=null;finishedAt:number|null=null;
  constructor(readonly enabled=true,readonly id:CourseId='training-straight') {}
  get definition(){return getCourse(this.id);}
  update(previous:V3,current:V3,time:number,dt:number,previousQ:Q4=[1,0,0,0],currentQ:Q4=previousQ) {
    if(this.invalid||!this.enabled||this.next>=this.definition.gates.length)return false;
    let alpha:number;
    if(this.id!=='training-straight'){const hit=intersectGate(this.definition.gates[this.next],previous,current,previousQ,currentQ);if(hit===null)return false;alpha=hit;}else{
    const g=GATES[this.next],x=g.center[0];
    if(previous[0]>=x||current[0]<x||current[0]<=previous[0])return false;
    alpha=(x-previous[0])/(current[0]-previous[0]);
    const y=previous[1]+alpha*(current[1]-previous[1]),z=previous[2]+alpha*(current[2]-previous[2]);
    const margin=.17;
    if(Math.abs(y-g.center[1])>g.width/2-margin||Math.abs(z-g.center[2])>g.height/2-margin)return false;
    }
    if(this.startedAt===null)this.startedAt=Math.max(0,time-dt+alpha*dt);
    const elapsed=Math.max(0,time-dt+alpha*dt)-this.startedAt;
    this.splits.push({gate:this.next+1,elapsed,sector:elapsed-(this.splits.at(-1)?.elapsed??0)});
    this.next++;
    if(this.next===this.definition.gates.length)this.finishedAt=Math.max(0,time-dt+alpha*dt);
    return true;
  }
  elapsed(time:number) {return this.startedAt===null?0:(this.finishedAt??time)-this.startedAt;}
}
