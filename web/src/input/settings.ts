import { clamp } from '../physics/math';
export interface AxisSetting { index:number; center:number; min:number; max:number; inverted:boolean }
export interface Settings {
  layout:'console'|'mode2'; throttleMode:'integrated'|'absolute'; deadzone:number; expo:number; rate:number;
  axes:Record<'roll'|'pitch'|'yaw'|'throttle',AxisSetting>;
  fov:number; quality:'auto'|'high'|'low'; sound:boolean;
}
export const DEFAULT_SETTINGS: Settings={
  layout:'console',throttleMode:'integrated',deadzone:.08,expo:.25,rate:3.5,
  axes:{roll:{index:2,center:0,min:-1,max:1,inverted:false},pitch:{index:3,center:0,min:-1,max:1,inverted:true},yaw:{index:0,center:0,min:-1,max:1,inverted:true},throttle:{index:1,center:0,min:-1,max:1,inverted:true}},
  fov:100,quality:'auto',sound:false,
};
export const cloneSettings=()=>structuredClone(DEFAULT_SETTINGS);
export function validatedSettings(value: unknown): Settings {
  if(!value||typeof value!=='object')return cloneSettings();
  const v=value as Settings,s=cloneSettings();
  s.layout=v.layout==='mode2'?'mode2':'console';s.throttleMode=v.throttleMode==='absolute'?'absolute':'integrated';
  for(const [k,a,b] of [['deadzone',0,.35],['expo',0,.9],['rate',1,10],['fov',65,125]] as const)
    if(Number.isFinite(v[k]))s[k]=clamp(v[k],a,b);
  s.quality=['auto','high','low'].includes(v.quality)?v.quality:'auto';s.sound=v.sound===true;
  for(const key of ['roll','pitch','yaw','throttle'] as const) {
    const axis=v.axes?.[key];
    if(axis&&Number.isInteger(axis.index)&&axis.index>=0&&axis.index<=7&&Number.isFinite(axis.center)&&Math.abs(axis.center)<=.5&&Number.isFinite(axis.min)&&Number.isFinite(axis.max)&&axis.min<axis.center-.1&&axis.max>axis.center+.1) {
      s.axes[key]={index:axis.index,center:axis.center,min:clamp(axis.min,-1,0),max:clamp(axis.max,0,1),inverted:axis.inverted===true};
    }
  }
  return s;
}
export const SETTINGS_KEY='physical-fpv-settings-v1';
export function loadSettings(storage: Pick<Storage,'getItem'>) {try{return validatedSettings(JSON.parse(storage.getItem(SETTINGS_KEY)||'null'));}catch{return cloneSettings();}}
export function saveSettings(storage: Pick<Storage,'setItem'>,s: Settings) {try{storage.setItem(SETTINGS_KEY,JSON.stringify(s));return true;}catch{return false;}}
export function shapeAxis(raw:number,axis:AxisSetting,deadzone:number,expo:number) {
  // Fail closed for direct UI callers as well as validated persisted settings.
  if(!Number.isFinite(raw)||![axis.center,axis.min,axis.max,deadzone,expo].every(Number.isFinite)||axis.min>=axis.center||axis.max<=axis.center||deadzone<0||deadzone>=1||expo<0||expo>1)return 0;
  const delta=raw-axis.center;
  const normalized=clamp(delta/(delta>=0?axis.max-axis.center:axis.center-axis.min),-1,1)*(axis.inverted?-1:1);
  const x=Math.max(0,(Math.abs(normalized)-deadzone)/(1-deadzone))*Math.sign(normalized);
  return x===0?0:(1-expo)*x+expo*x*x*x;
}
