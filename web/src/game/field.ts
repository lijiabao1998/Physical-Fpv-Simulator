import type { V3 } from '../physics/math';
export interface FieldBox { center: V3; half: V3; color: string; kind:'gate'|'crate'|'hangar'|'barrier' }
export interface Gate { center: V3; width:number; height:number; depth:number }
export const GATES: Gate[] = [
  {center:[10,0,2.1],width:4.2,height:4.2,depth:.22},
  {center:[23,-4,2.6],width:4.2,height:4.8,depth:.22},
  {center:[36,1,3.1],width:4.4,height:5.4,depth:.22},
  {center:[50,6,2.6],width:4.2,height:4.8,depth:.22},
  {center:[65,0,2.1],width:4.8,height:4.2,depth:.22},
];
export const FIELD_BOXES: FieldBox[] = GATES.flatMap<FieldBox>(g=>{
  const [x,y,z]=g.center,bottom=z-g.height/2;
  return [
    {center:[x,y-g.width/2,bottom+g.height/2] as V3,half:[g.depth/2,.10,g.height/2] as V3,color:'#f47b36',kind:'gate' as const},
    {center:[x,y+g.width/2,bottom+g.height/2] as V3,half:[g.depth/2,.10,g.height/2] as V3,color:'#f47b36',kind:'gate' as const},
    {center:[x,y,bottom+g.height] as V3,half:[g.depth/2,g.width/2+.1,.10] as V3,color:'#f47b36',kind:'gate' as const},
  ];
}).concat([
  {center:[-1,13,2] as V3,half:[5,.15,2] as V3,color:'#d4d0ba',kind:'hangar'},
  {center:[-6,9,2] as V3,half:[.15,4,2] as V3,color:'#d4d0ba',kind:'hangar'},
  {center:[4,9,2] as V3,half:[.15,4,2] as V3,color:'#d4d0ba',kind:'hangar'},
  {center:[-1,9,4.1] as V3,half:[5.1,4.1,.15] as V3,color:'#404b48',kind:'hangar'},
  {center:[7,7,.55] as V3,half:[.65,.65,.55] as V3,color:'#9a774f',kind:'crate'},
  {center:[8.3,8,.5] as V3,half:[.5,.5,.5] as V3,color:'#a8885d',kind:'crate'},
  {center:[27,6,.6] as V3,half:[1.5,.3,.6] as V3,color:'#d8c9a8',kind:'barrier'},
  {center:[42,-6,.55] as V3,half:[.7,.7,.55] as V3,color:'#a8885d',kind:'crate'},
] as FieldBox[]);
export const TREES: {position:V3; height:number}[] = Array.from({length:52},(_,i)=>{
  const seed=(i*17.3)%19;
  const angle=i*2.39996;
  const r=42+(i%5)*12;
  return {position:[25+Math.cos(angle)*r,Math.sin(angle)*r,0],height:5+seed*.3};
}).filter(t=>Math.abs(t.position[1])>14||t.position[0]<-15||t.position[0]>85) as {position:V3;height:number}[];
