import { clamp } from '../physics/math';
import { ZERO,type Controls } from '../physics/controller';
import { shapeAxis,type Settings } from './settings';

export type InputAction='arm'|'disarm'|'camera'|'pause'|'reset'|'mode';
export interface InputFrame {controls:Controls;actions:InputAction[]; source:'keyboard'|'touch'|'gamepad';device:string;supported:boolean;raw:number[];buttons:number[]}
export interface PadLike {id:string;index:number;connected:boolean;mapping:string;axes:readonly number[];buttons:readonly {value:number;pressed:boolean}[];timestamp:number}
export class InputManager {
  keys=new Set<string>(); throttle=0;
  touch: Controls={...ZERO}; touchActive=false;
  padIndex: number|null=null;
  private padId:string|null=null;
  private previous=new Set<number>();private holdStart: number|null=null;private armSent=false;
  private armReleased=false;
  private throttleCaptured=false;
  constructor(public settings:Settings,private readonly onFail:(reason:string)=>void) {}
  clear() {this.keys.clear();this.throttle=0;this.touch={...ZERO};this.touchActive=false;this.previous.clear();this.holdStart=null;this.armSent=false;this.throttleCaptured=false;this.armReleased=false;}
  fail(reason:string){this.clear();this.onFail(reason);}
  sample(pads:readonly (PadLike|null)[],dt:number,nowMs:number):InputFrame {
    const pad=pads.find(p=>p?.connected&&p.index===this.padIndex&&p.id===this.padId)??pads.find(p=>p?.connected)??null;
    const actions:InputAction[]=[];
    if(this.padIndex!==null&&(!pad||pad.index!==this.padIndex||pad.id!==this.padId)){
      this.padIndex=null;this.padId=null;this.fail(pad?'Controller replaced — stopped and disarmed':'Controller disconnected — stopped and disarmed');
    }
    const c:Controls={...ZERO};
    let device='Keyboard',source:InputFrame['source']='keyboard',supported=true,raw:number[]=[],buttons:number[]=[];
    if(pad) {
      source='gamepad';device=pad.id;raw=Array.from(pad.axes);buttons=pad.buttons.map(b=>b.value);
      const newlyConnected=this.padIndex===null;this.padIndex=pad.index;this.padId=pad.id;
      supported=pad.mapping==='standard'&&pad.axes.length>=4&&pad.buttons.length>=10;
      if(newlyConnected){this.clear();this.onFail('Controller connected — release ARM and zero throttle, then hold ARM for 0.6 s');}
      if(!supported) {
        this.fail('Unsupported mapping — use a standard-mapped controller or keyboard');
        return {controls:c,actions,source,device,supported,raw,buttons};
      }
      const hasBad=raw.some(x=>!Number.isFinite(x)||Math.abs(x)>1.01)||buttons.some(x=>!Number.isFinite(x)||x<0||x>1.01);
      if(hasBad){this.fail('Invalid controller data — disarmed');return {controls:c,actions,source,device,supported:false,raw,buttons};}
      // W3C timestamp is input-update time, not a heartbeat. Fresh API presence,
      // connected, mapping and finite controls establish availability.
      const required=this.settings.layout==='mode2'?['roll','pitch','yaw','throttle'] as const:['roll','pitch','yaw'] as const;
      if(required.some(k=>!Number.isInteger(this.settings.axes[k].index)||this.settings.axes[k].index<0||this.settings.axes[k].index>=raw.length)){this.fail('Calibration axis unavailable — disarmed');return {controls:c,actions,source,device,supported:false,raw,buttons};}
      for(const key of ['roll','pitch','yaw'] as const) {
        const a=this.settings.axes[key];c[key]=shapeAxis(raw[a.index]??NaN,a,this.settings.deadzone,this.settings.expo);
      }
      if(this.settings.layout==='console') c.throttle=clamp(buttons[7]??0,0,1);
      else {
        const a=this.settings.axes.throttle;
        const stick=shapeAxis(raw[a.index]??NaN,a,this.settings.deadzone,this.settings.expo);
        if(this.settings.throttleMode==='absolute')c.throttle=(stick+1)/2;
        else {this.throttle=clamp(this.throttle+stick*dt*.55,0,1);c.throttle=this.throttle;}
      }
      // Require observing zero after connect/reset; a held trigger/stick never arms.
      if(c.throttle<.025)this.throttleCaptured=true;
      const pressed=new Set(pad.buttons.map((b,i)=>b.pressed?i:-1).filter(i=>i>=0));
      for(const [i,action] of [[1,'disarm'],[3,'camera'],[9,'pause'],[8,'reset']] as const)
        if(pressed.has(i)&&!this.previous.has(i))actions.push(action);
      if(!pressed.has(0))this.armReleased=true;
      if(pressed.has(0)&&this.armReleased&&c.throttle<.025&&this.throttleCaptured) {
        if(this.holdStart===null)this.holdStart=nowMs;
        if(nowMs-this.holdStart>=600&&!this.armSent){actions.push('arm');this.armSent=true;}
      } else {this.holdStart=null;this.armSent=false;}
      this.previous=pressed;
    } else if(this.touchActive) {Object.assign(c,this.touch);source='touch';device='Touch controls';}
    else {
      this.throttle=clamp(this.throttle+((this.keys.has('ArrowUp')?1:0)-(this.keys.has('ArrowDown')?1:0))*dt*.45,0,1);
      c.throttle=this.throttle;c.roll=(+this.keys.has('KeyD')-+this.keys.has('KeyA'))*.65;
      c.pitch=(+this.keys.has('KeyW')-+this.keys.has('KeyS'))*.65;
      c.yaw=(+this.keys.has('KeyQ')-+this.keys.has('KeyE'))*.65;
    }
    return {controls:c,actions,source,device,supported,raw,buttons};
  }
}
