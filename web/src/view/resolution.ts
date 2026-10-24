/** Conservative Auto pixel workload; manual High stays native, physics unaffected. */
export function renderPixelRatio(width:number,height:number,dpr:number,autoLow:boolean,low:boolean){
 const native=Math.min(Math.max(.1,Number.isFinite(dpr)?dpr:1),low?1:1.5);
 if(!autoLow)return native;
 const area=Math.max(1,width)*Math.max(1,height);
 return Math.min(native,Math.sqrt(480000/area));
}
