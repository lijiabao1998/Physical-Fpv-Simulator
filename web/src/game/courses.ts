import {FIELD_BOXES,GATES,TREES,type FieldBox} from './field';
import {add,rotate,type Q4,type V3} from '../physics/math';
import type {OrientedGate} from './gate-geometry';
export type CourseId='training-straight'|'british-slalom'|'industrial-run';
export interface CourseBox extends FieldBox {rotation?:Q4;gateIndex?:number}
export interface CourseDefinition {id:CourseId;version:string;name:string;description:string;gates:OrientedGate[];boxes:CourseBox[];trees:typeof TREES}
export function gateRotation(yaw:number,pitch=0):Q4{return [Math.cos(yaw/2)*Math.cos(pitch/2),-Math.sin(yaw/2)*Math.sin(pitch/2),Math.cos(yaw/2)*Math.sin(pitch/2),Math.sin(yaw/2)*Math.cos(pitch/2)];}
const gate=(center:V3,yaw:number,pitch=0,width=4.4,height=4.4):OrientedGate=>({center,rotation:gateRotation(yaw,pitch),width,height,depth:.24});
export function gateBoxes(gates:OrientedGate[]):CourseBox[]{return gates.flatMap((g,gateIndex)=>[
 {offset:[0,-g.width/2,0] as V3,half:[g.depth/2,.10,g.height/2] as V3},
 {offset:[0,g.width/2,0] as V3,half:[g.depth/2,.10,g.height/2] as V3},
 {offset:[0,0,g.height/2] as V3,half:[g.depth/2,g.width/2+.10,.10] as V3},
 {offset:[0,0,-g.height/2] as V3,half:[g.depth/2,g.width/2+.10,.10] as V3},
 ].map(b=>({center:add(g.center,rotate(g.rotation,b.offset)),half:b.half,rotation:g.rotation,color:'#f47b36',kind:'gate' as const,gateIndex})));}
const training:CourseDefinition={id:'training-straight',version:'training-five-v1',name:'Training Straight',description:'Original five-gate baseline, preserved.',gates:GATES.map(g=>({...g,rotation:[1,0,0,0]})),boxes:FIELD_BOXES,trees:TREES};
const slalomGates=[gate([10,0,2.8],0),gate([22,8,5.5],.8,-.18),gate([30,-5,9],-.9,-.35),gate([20,-19,6],-2.2,.3),gate([3,-15,3],2.8,.15),gate([1,4,5],1.2,-.2),gate([16,18,8],.5,-.15)];
const countryBuildings:CourseBox[]=[];
for(const [x,y] of [[-21,7],[41,-17],[38,25]]){
 countryBuildings.push({center:[x,y,2],half:[2.5,1.8,2],color:'#a77b60',kind:'hangar'});
 for(const sign of [-1,1])countryBuildings.push({center:[x,y+sign*.9,4.45],half:[2.7,1.1,.12],rotation:[Math.cos(.28),-sign*Math.sin(.28),0,0],color:'#46534e',kind:'hangar'});
 countryBuildings.push({center:[x-1,y,5],half:[.25,.3,1],color:'#8f6853',kind:'hangar'});
 for(const offset of [-1.3,1.3])countryBuildings.push({center:[x+offset,y-1.82,2.3],half:[.45,.025,.65],color:'#cfdfd4',kind:'barrier'});
 countryBuildings.push({center:[x,y-1.82,1],half:[.4,.025,1],color:'#3e554a',kind:'barrier'});
}
const slalom:CourseDefinition={id:'british-slalom',version:'british-slalom-v1',name:'British Slalom',description:'Country turns, climbing gates and a descending hairpin. Follow orange gate normals.',gates:slalomGates,boxes:[...gateBoxes(slalomGates),...countryBuildings],trees:TREES};
const industrialGates=[gate([10,0,2.1],0,0,4,3.6),gate([20,0,2.3],0,0,3.6,3.6),gate([32,0,2.3],0,0,3.6,3.6),gate([38,16,3.3],Math.PI/2,0,3.6,3.4),gate([38,28,3.5],Math.PI/2,0,3.6,3.4),gate([25,32,6],2.6,-.2),gate([10,23,3],-2.5,.3)];
// Every structural surface below is rendered and instantiated as the same static
// Rapier cuboid. Open ends are genuine openings, not invisible pass-through walls.
const industrialBuildings:CourseBox[]=[];
const structure=(center:V3,half:V3,color:string,rotation?:Q4)=>industrialBuildings.push({center,half,color,rotation,kind:'hangar'});
for(const sign of [-1,1]){
 structure([21,sign*4,2.5],[9,.18,2.5],'#96654d');
 for(const x of [12,18,24,30])structure([x,sign*3.75,2.6],[.16,.22,2.6],'#455657');
 structure([21,sign*2,5.6],[9.3,2.2,.14],'#505b61',[Math.cos(.15),-sign*Math.sin(.15),0,0]);
 // Transverse shed, its open ends face north and south.
 structure([38+sign*3.2,19,2.8],[.18,7,2.8],'#a27354');
 for(const y of [12,19,26])structure([38+sign*2.95,y,2.9],[.2,.16,2.9],'#455657');
 structure([38+sign*1.6,19,6.05],[1.8,7.3,.14],'#505b61',[Math.cos(.15),0,sign*Math.sin(.15),0]);
}
for(const x of [12,17.5,30])structure([x,0,4.65],[.16,4,.22],'#455657');
structure([25,0,.4],[.25,2.7,.4],'#c4a147');
for(const y of [12,20,26])structure([38,y,5.15],[3.2,.16,.22],'#455657');
structure([38,23,.5],[2.3,.25,.5],'#c4a147');
const industrial:CourseDefinition={id:'industrial-run',version:'industrial-run-v1',name:'Industrial Run',description:'Open-ended brick warehouses, steel beams and low barriers. Structural meshes have matching static collisions.',gates:industrialGates,boxes:[...gateBoxes(industrialGates),...industrialBuildings],trees:[]};
export const COURSES:readonly CourseDefinition[]=[training,slalom,industrial];
export function getCourse(id:string='training-straight',version?:string):CourseDefinition{const c=COURSES.find(c=>c.id===id);if(!c||version!==undefined&&version!==c.version)throw Error('Unknown course ID/version');return c;}
