import {Powertrain,type PowerOutput} from './powertrain';
import {DEFAULT_MODEL,RHO,validateDt,type Model} from './config';
import {finiteRange} from './math';
export const G08_MODEL='g08-transient-v1' as const;
export const G07_MODEL='g07-quasistatic-v1' as const;
export type PhysicsModel=typeof G08_MODEL|typeof G07_MODEL;
/** Synthetic one-quadrant drive; no inductance, regenerative braking or calibrated ESC. */
export const TRANSIENT={motorInertia:1.2e-6,currentLimit:60,maxElectricalStep:1/1920,rm:.060,re:.008,friction:1e-6} as const;
export interface TransientOutput extends PowerOutput {effectiveDuty:number[];reactionTorque:number[];rotorAngularMomentum:number;rotorEnergy:number;rotorStoragePower:number}
const root=(a:number,b:number,c:number)=>2*c/(b+Math.sqrt(b*b+4*a*c));
export class TransientPowertrain extends Powertrain {
  readonly physicsModel=G08_MODEL;
  readonly rotorInertia:number;
  rotorOmega=[0,0,0,0];
  rotorStorageJ=0;
  constructor(model:Model=DEFAULT_MODEL){super(model);this.rotorInertia=TRANSIENT.motorInertia+model.propMass*model.diameter**2/12;this.last=this.coastOutput();}
  /** Equilibrium evaluate()/hover() intentionally remain the immutable G07 solver.
   * Dynamic state is advanced only by step(); evaluate is not a transient sample. */
  coastOutput():TransientOutput {
    const w=this.rotorOmega??[0,0,0,0],q=.012*RHO*this.model.diameter**5/(2*Math.PI)**2;
    const tf=.11*RHO*this.model.diameter**4/(2*Math.PI)**2;
    const torque=w.map(x=>q*x*x),frictionPower=TRANSIENT.friction*w.reduce((s,x)=>s+x*x,0);
    const rotorPower=torque.reduce((s,x,i)=>s+x*w[i],0);
    return {voltage:4*(3.1+1.1*this.soc),current:0,rpm:w.map(x=>x*60/(2*Math.PI)),omega:[...w],thrust:w.map(x=>tf*x*x),torque,motorCurrent:[0,0,0,0],chemicalPower:0,busPower:0,packHeat:0,copperHeat:0,escHeat:0,frictionPower,rotorPower,residual:0,powerError:0,
      effectiveDuty:[0,0,0,0],reactionTorque:w.map(x=>-TRANSIENT.friction*x),rotorAngularMomentum:(this.rotorInertia??0)*(-w[0]+w[1]-w[2]+w[3]),rotorEnergy:.5*(this.rotorInertia??0)*w.reduce((s,x)=>s+x*x,0),rotorStoragePower:-frictionPower-rotorPower};
  }
  override step(d:number[],dt:number,airspeed=0):TransientOutput {
    if(d.length!==4)throw Error('Exactly four duties required');d.forEach(x=>finiteRange(x,0,1,'ESC duty'));
    validateDt(dt);finiteRange(airspeed,0,150,'airspeed');
    // Stage all state so every domain failure is atomic.
    let w=[...this.rotorOmega],soc=this.soc,temp=this.temperature;
    const accum={chemical:0,bus:0,pack:0,copper:0,esc:0,friction:0,aero:0,charge:0,cooling:0,cell:0};
    const n=Math.ceil(dt/TRANSIENT.maxElectricalStep),h=dt/n,J=this.rotorInertia,C=this.model.capacityAh*3600;
    const {rm,re,friction,currentLimit}=TRANSIENT,r=rm+re,k=this.model.motorK;
    const tq=.012*RHO*this.model.diameter**5/(2*Math.PI)**2,tf=.11*RHO*this.model.diameter**4/(2*Math.PI)**2;
    const average={thrust:[0,0,0,0],torque:[0,0,0,0],reactionTorque:[0,0,0,0],momentum:0};
    let out:TransientOutput=this.coastOutput();
    for(let s=0;s<n;s++) {
      const ocv0=4*(3.1+1.1*soc),batteryR=this.resistance+2.2*h/C;
      const loads=(v:number)=>{
        const wm:number[]=[],im:number[]=[],eff:number[]=[];
        for(let i=0;i<4;i++){
          let m=root(h*tq/(2*J),1+h*(friction+k*k/r)/(2*J),w[i]+h*k*d[i]*v/(2*J*r));
          let current=(d[i]*v-k*m)/r;
          if(current<0){current=0;m=root(h*tq/(2*J),1+h*friction/(2*J),w[i]);}
          else if(current>currentLimit){current=currentLimit;m=root(h*tq/(2*J),1+h*friction/(2*J),w[i]+h*k*current/(2*J));}
          wm.push(m);im.push(current);eff.push(current===0?0:(k*m+r*current)/v);
        }
        const current=im.reduce((sum,x,i)=>sum+x*eff[i],0);
        return {wm,im,eff,current};
      };
      let lo=0,hi=ocv0,v=ocv0;
      for(let j=0;j<44;j++){v=(lo+hi)/2;const l=loads(v);if(v+batteryR*l.current>ocv0)hi=v;else lo=v;}
      const l=loads(v),midSoc=soc-h*l.current/(2*C),ocv=4*(3.1+1.1*midSoc);
      const nextW=l.wm.map((m,i)=>2*m-w[i]),nextSoc=soc-h*l.current/C;
      finiteRange(nextSoc,.05,1,'synthetic SOC');nextW.forEach(x=>finiteRange(x,0,5000,'rotor speed'));
      const sq=l.im.reduce((sum,x)=>sum+x*x,0),torque=l.wm.map(x=>tq*x*x);
      const chemicalPower=ocv*l.current,packHeat=l.current*l.current*this.resistance,copperHeat=rm*sq,escHeat=re*sq;
      const frictionPower=friction*l.wm.reduce((sum,x)=>sum+x*x,0),rotorPower=torque.reduce((sum,x,i)=>sum+x*l.wm[i],0);
      const storage=J*nextW.reduce((sum,x,i)=>sum+(x*x-w[i]*w[i])/(2*h),0);
      const reactionTorque=l.wm.map((m,i)=>k*l.im[i]-friction*m);
      const momentum=J*(-l.wm[0]+l.wm[1]-l.wm[2]+l.wm[3]);
      for(let i=0;i<4;i++){average.thrust[i]+=tf*l.wm[i]**2/n;average.torque[i]+=torque[i]/n;average.reactionTorque[i]+=reactionTorque[i]/n;}average.momentum+=momentum/n;
      const hc=.12+.02*airspeed,cellHeat=(l.current/2)**2*.020;
      const nextT=temp+h*(cellHeat-hc*(temp-298.15))/(45+.5*h*hc);finiteRange(nextT,273.15,333.15,'synthetic cell temperature');
      accum.chemical+=h*chemicalPower;accum.bus+=h*v*l.current;accum.pack+=h*packHeat;accum.copper+=h*copperHeat;accum.esc+=h*escHeat;accum.friction+=h*frictionPower;accum.aero+=h*rotorPower;accum.charge+=h*l.current;accum.cell+=h*8*cellHeat;accum.cooling+=h*8*hc*((temp+nextT)/2-298.15);
      out={voltage:v,current:l.current,rpm:nextW.map(x=>x*60/(2*Math.PI)),omega:nextW,thrust:average.thrust,torque:average.torque,motorCurrent:l.im,chemicalPower,busPower:v*l.current,packHeat,copperHeat,escHeat,frictionPower,rotorPower,residual:v+this.resistance*l.current-ocv,powerError:chemicalPower-packHeat-copperHeat-escHeat-frictionPower-rotorPower-storage,effectiveDuty:l.eff,reactionTorque:average.reactionTorque,rotorAngularMomentum:average.momentum,rotorEnergy:.5*J*nextW.reduce((sum,x)=>sum+x*x,0),rotorStoragePower:storage};
      w=nextW;soc=nextSoc;temp=nextT;
    }
    this.rotorOmega=w;this.soc=soc;this.temperature=temp;
    this.chemicalJ+=accum.chemical;this.busJ+=accum.bus;this.packHeatJ+=accum.pack;this.copperJ+=accum.copper;this.escJ+=accum.esc;this.frictionJ+=accum.friction;this.rotorJ+=accum.aero;this.chargeC+=accum.charge;this.cellHeatJ+=accum.cell;this.coolingJ+=accum.cooling;
    this.rotorStorageJ=out.rotorEnergy;this.last=out;return out;
  }
  override audit(){const a=super.audit();return {...a,physicsModel:G08_MODEL,syntheticParameters:true,rotorKineticJ:this.rotorStorageJ,energyError:a.energyError-this.rotorStorageJ};}
}
/** Explicit stationary, externally clamped four-rotor bench fixture.
 * Not a flight/contact-jam mode. Clamp angular work is zero; all input becomes heat.
 * This is synthetic circuit analysis, not measured stall current or blade stall. */
export function lockedRotorBench(d:number[],soc=.9,model:Model=DEFAULT_MODEL){
 if(d.length!==4)throw Error('Exactly four duties required');d.forEach(x=>finiteRange(x,0,1,'ESC duty'));finiteRange(soc,.05,1,'synthetic SOC');
 const p=new Powertrain(model),ocv=4*(3.1+1.1*soc),r=TRANSIENT.rm+TRANSIENT.re;
 const loads=(v:number)=>{const motorCurrent=d.map(x=>Math.min(TRANSIENT.currentLimit,x*v/r));const duty=motorCurrent.map((x,i)=>x===0?0:Math.min(d[i],r*x/v));return {motorCurrent,effectiveDuty:duty,current:motorCurrent.reduce((s,x,i)=>s+x*duty[i],0)};};
 let lo=0,hi=ocv,v=ocv;
 for(let i=0;i<48;i++){v=(lo+hi)/2;if(v+p.resistance*loads(v).current>ocv)hi=v;else lo=v;}
 const l=loads(v),sq=l.motorCurrent.reduce((s,x)=>s+x*x,0);
 const chemicalPower=ocv*l.current,packHeat=p.resistance*l.current*l.current,copperHeat=TRANSIENT.rm*sq,escHeat=TRANSIENT.re*sq;
 return {fixture:'externally-clamped-stationary-rotors',synthetic:true,voltage:v,current:l.current,motorCurrent:l.motorCurrent,effectiveDuty:l.effectiveDuty,omega:[0,0,0,0],clampTorque:l.motorCurrent.map(x=>model.motorK*x),mechanicalPower:0,chemicalPower,packHeat,copperHeat,escHeat,powerError:chemicalPower-packHeat-copperHeat-escHeat};
}
