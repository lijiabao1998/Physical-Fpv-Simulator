import {assemblyModel,type Assembly} from '../physics/config';
import {G07_MODEL,G08_MODEL,type PhysicsModel} from '../physics/transient';
import {COURSE_VERSION,type GateSplit} from './course';
export function recordKey(model:PhysicsModel,assembly:Assembly,course=COURSE_VERSION){
  assemblyModel(assembly);
  if(![G07_MODEL,G08_MODEL].includes(model)||course!==COURSE_VERSION)throw Error('Unknown race class');
  return ['physical-fpv-race-v1',course,model,assembly.frame,assembly.battery,assembly.motor,assembly.propeller].join(':');
}
export interface RaceRecord {total:number;splits:GateSplit[]}
function valid(r:RaceRecord){return r&&Number.isFinite(r.total)&&r.total>0&&Array.isArray(r.splits)&&r.splits.length===5&&r.splits.every((s,i)=>s.gate===i+1&&Number.isFinite(s.elapsed)&&Number.isFinite(s.sector)&&s.sector>=0&&s.elapsed>=0&&Math.abs(s.elapsed-(i?r.splits[i-1].elapsed:0)-s.sector)<1e-9)&&r.splits[0].elapsed===0&&Math.abs(r.splits[4].elapsed-r.total)<1e-9;}
export function loadRecord(storage:Pick<Storage,'getItem'>,model:PhysicsModel,assembly:Assembly):RaceRecord|null{
  try{const r=JSON.parse(storage.getItem(recordKey(model,assembly))??'null');return valid(r)?r:null;}catch{return null;}
}
export function saveRecord(storage:Pick<Storage,'getItem'|'setItem'>,model:PhysicsModel,assembly:Assembly,record:RaceRecord){
  if(!valid(record))return null;
  const old=loadRecord(storage,model,assembly);if(old&&old.total<=record.total)return old;
  try{storage.setItem(recordKey(model,assembly),JSON.stringify(record));return structuredClone(record);}catch{return null;}
}
