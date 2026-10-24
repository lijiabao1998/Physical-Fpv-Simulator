/** Optional bounded local measurements; never affects simulation clocks. */
export class FlightDiagnostics {
  enabled=false;
  private frames:number[]=[];private physics:number[]=[];private render:number[]=[];
  lastSteps=0;maxSteps=0;lastStop='None';
  setEnabled(value:boolean){this.enabled=value;if(!value){this.frames=[];this.physics=[];this.render=[];this.lastSteps=0;this.maxSteps=0;}}
  record(frameMs:number,physicsMs:number,steps:number,renderMs:number){
    if(!this.enabled)return;
    if(![frameMs,physicsMs,steps,renderMs].every(Number.isFinite)||frameMs<0||physicsMs<0||renderMs<0||!Number.isInteger(steps)||steps<0)return;
    const add=(a:number[],v:number)=>{a.push(v);if(a.length>240)a.shift();};
    add(this.frames,frameMs);add(this.render,renderMs);if(steps)add(this.physics,physicsMs/steps);
    this.lastSteps=steps;this.maxSteps=Math.max(this.maxSteps,steps);
  }
  snapshot(){const mean=(a:number[])=>a.length?a.reduce((s,x)=>s+x,0)/a.length:0;
    const frameMs=mean(this.frames);return {enabled:this.enabled,samples:this.frames.length,fps:frameMs?1000/frameMs:0,frameMs,physicsStepMs:mean(this.physics),renderCpuMs:mean(this.render),lastSteps:this.lastSteps,maxSteps:this.maxSteps,lastStop:this.lastStop};}
}
