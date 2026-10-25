import {assemblyModel,type Assembly} from '../physics/config';
import {G07_MODEL,G08_MODEL,type PhysicsModel} from '../physics/transient';
import {COURSES} from './courses';
import {COURSE_VERSION,type GateSplit} from './course';
export function recordKey(model:PhysicsModel,assembly:Assembly,course=COURSE_VERSION){
  assemblyModel(assembly);
  if(![G07_MODEL,G08_MODEL].includes(model)||!COURSES.some(c=>c.version===course))throw Error('Unknown race class');
  const id=COURSES.find(c=>c.version===course)!.id;
  return ['physical-fpv-race-v1',...(id==='training-straight'?[]:[id]),course,model,assembly.frame,assembly.battery,assembly.motor,assembly.propeller].join(':');
}
export interface RaceRecord {total:number;splits:GateSplit[]}
function valid(r:RaceRecord,count=5){return count>0&&r&&Number.isFinite(r.total)&&r.total>0&&Array.isArray(r.splits)&&r.splits.length===count&&r.splits.every((s,i)=>s.gate===i+1&&Number.isFinite(s.elapsed)&&Number.isFinite(s.sector)&&s.sector>=0&&s.elapsed>=0&&Math.abs(s.elapsed-(i?r.splits[i-1].elapsed:0)-s.sector)<1e-9)&&r.splits[0].elapsed===0&&Math.abs(r.splits[count-1].elapsed-r.total)<1e-9;}
export function loadRecord(storage:Pick<Storage,'getItem'>,model:PhysicsModel,assembly:Assembly,course=COURSE_VERSION):RaceRecord|null{
  try{const r=JSON.parse(storage.getItem(recordKey(model,assembly,course))??'null');return valid(r,COURSES.find(c=>c.version===course)?.gates.length??0)?r:null;}catch{return null;}
}
export function saveRecord(storage:Pick<Storage,'getItem'|'setItem'>,model:PhysicsModel,assembly:Assembly,record:RaceRecord,course=COURSE_VERSION){
  if(!valid(record,COURSES.find(c=>c.version===course)?.gates.length??0))return null;
  const old=loadRecord(storage,model,assembly,course);if(old&&old.total<=record.total)return old;
  try{storage.setItem(recordKey(model,assembly,course),JSON.stringify(record));return structuredClone(record);}catch{return null;}
}
