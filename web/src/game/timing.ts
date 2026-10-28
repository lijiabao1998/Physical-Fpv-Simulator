import {FIXED_DT} from '../physics/config';
/** Rendering may batch fixed steps, never enlarge the physical integration step. */
export function planPhysicsSteps(accumulator:number,elapsed:number,active:boolean) {
  if(!Number.isFinite(elapsed)||elapsed<0||elapsed>.25)return {steps:0,remainder:0,fault:'Frame interruption over 250 ms — paused and disarmed.'};
  if(!active)return {steps:0,remainder:0,fault:null};
  if(!Number.isFinite(accumulator)||accumulator<0)return {steps:0,remainder:0,fault:'Invalid physics clock — paused and disarmed.'};
  const total=accumulator+elapsed;
  // Epsilon only compensates arithmetic at exact tick boundaries; dt stays fixed.
  const steps=Math.floor((total+1e-12)/FIXED_DT);
  if(steps>60)return {steps:0,remainder:0,fault:'Physics catch-up limit — paused and disarmed.'};
  return {steps,remainder:Math.max(0,total-steps*FIXED_DT),fault:null};
}

/** A previously queued rAF timestamp can precede an explicit initialization anchor.
 * Ignore its negative elapsed time without ever moving the anchor backwards. */
export function advanceRenderClock(previousMs:number,callbackMs:number){
 return {anchor:Math.max(previousMs,callbackMs),elapsed:previousMs?Math.max(0,(callbackMs-previousMs)/1000):0};
}
