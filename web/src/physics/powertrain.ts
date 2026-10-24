import { DEFAULT_MODEL, INITIAL_SOC, RHO, validateDt, type Model } from './config';
import { finiteRange } from './math';

export interface PowerOutput {
  voltage: number; current: number; rpm: number[]; omega: number[];
  thrust: number[]; torque: number[]; motorCurrent: number[];
  chemicalPower: number; busPower: number; packHeat: number;
  copperHeat: number; escHeat: number; frictionPower: number; rotorPower: number;
  residual: number; powerError: number;
}
export class Powertrain {
  soc = INITIAL_SOC;
  temperature = 298.15;
  chemicalJ=0; busJ=0; packHeatJ=0; copperJ=0; escJ=0; frictionJ=0; rotorJ=0;
  cellHeatJ=0; coolingJ=0; chargeC=0;
  last: PowerOutput;
  readonly resistance = 0.048; // 4S2P: 4*(.020+.001)/2 + .006 ohm
  constructor(readonly model: Model = DEFAULT_MODEL) { this.last=this.evaluate([0,0,0,0]); }
  private validate(d: number[]) {
    if (d.length!==4) throw Error('Exactly four duties required');
    d.forEach(v=>finiteRange(v,0,1,'ESC duty'));
  }
  private at(d: number[], soc: number): PowerOutput {
    finiteRange(soc,0.05,1,'synthetic SOC');
    const k=this.model.motorK, rm=.060, re=.008, friction=1e-6;
    const tq=.012*RHO*this.model.diameter**5/(2*Math.PI)**2;
    const tf=.11*RHO*this.model.diameter**4/(2*Math.PI)**2;
    const a=(rm+re)*tq/k, b=k+(rm+re)*friction/k;
    const ocv=4*(3.1+1.1*soc);
    const loads=(v: number) => {
      const omega=d.map(duty=>2*duty*v/(b+Math.sqrt(b*b+4*a*duty*v)));
      const torque=omega.map(w=>tq*w*w);
      const im=omega.map((w,i)=>(torque[i]+friction*w)/k);
      const current=im.reduce((s,x,i)=>s+d[i]*x,0);
      const slope=omega.reduce((s,w,i)=>s+d[i]**2*(2*tq*w+friction)/(k*(2*a*w+b)),0);
      return {omega,torque,im,current,slope};
    };
    let low=0,high=ocv,v=ocv,residual=0;
    for(let n=0;n<64;n++) {
      const l=loads(v); residual=v+this.resistance*l.current-ocv;
      if(Math.abs(residual)<1e-12) break;
      if(n===63) throw Error('Circuit root did not converge');
      if(residual>0) high=v; else low=v;
      const next=v-residual/(1+this.resistance*l.slope);
      v=next>low&&next<high?next:(low+high)/2;
    }
    const l=loads(v);
    if(l.im.some(i=>i>60)||l.omega.some(w=>w>5000)||l.current/2>60) throw Error('Synthetic motor/current domain exceeded');
    const squared=l.im.reduce((s,i)=>s+i*i,0);
    const packHeat=l.current*l.current*this.resistance;
    const copperHeat=rm*squared,escHeat=re*squared;
    const frictionPower=friction*l.omega.reduce((s,w)=>s+w*w,0);
    const rotorPower=l.torque.reduce((s,q,i)=>s+q*l.omega[i],0);
    const chemicalPower=ocv*l.current;
    return { voltage:v,current:l.current,rpm:l.omega.map(w=>w*60/(2*Math.PI)),omega:l.omega,
      thrust:l.omega.map(w=>tf*w*w),torque:l.torque,motorCurrent:l.im,
      chemicalPower,busPower:v*l.current,packHeat,copperHeat,escHeat,frictionPower,rotorPower,
      residual,powerError:chemicalPower-packHeat-copperHeat-escHeat-frictionPower-rotorPower };
  }
  evaluate(d: number[]) { this.validate(d); return this.at(d,this.soc); }
  step(d: number[],dt: number,airspeed=0) {
    this.validate(d); validateDt(dt); finiteRange(airspeed,0,150,'airspeed');
    let midSoc=this.soc;
    const capacity=this.model.capacityAh*3600;
    for(let n=0;n<32;n++) {
      const next=this.soc-0.5*dt*this.at(d,midSoc).current/capacity;
      if(Math.abs(next-midSoc)<2e-14) {midSoc=next; break;}
      midSoc=next;
      if(n===31) throw Error('SOC midpoint did not converge');
    }
    const mid=this.at(d,midSoc);
    const nextSoc=this.soc-dt*mid.current/capacity;
    const h=.12+.02*airspeed;
    const cellHeat=(mid.current/2)**2*.020;
    const nextT=this.temperature+dt*(cellHeat-h*(this.temperature-298.15))/(45+.5*dt*h);
    finiteRange(nextT,273.15,333.15,'synthetic cell temperature');
    const end=this.at(d,nextSoc); // guards before mutating state
    this.coolingJ+=dt*8*h*((this.temperature+nextT)/2-298.15);
    this.cellHeatJ+=dt*8*cellHeat;
    this.soc=nextSoc; this.temperature=nextT; this.chargeC+=dt*mid.current;
    this.chemicalJ+=dt*mid.chemicalPower; this.busJ+=dt*mid.busPower;
    this.packHeatJ+=dt*mid.packHeat;this.copperJ+=dt*mid.copperHeat;
    this.escJ+=dt*mid.escHeat;this.frictionJ+=dt*mid.frictionPower;this.rotorJ+=dt*mid.rotorPower;
    this.last=end; return end;
  }
  audit() {
    const stateJ=this.model.capacityAh*3600*4*(INITIAL_SOC-this.soc)*(3.1+1.1*(INITIAL_SOC+this.soc)/2);
    return { chemicalJ:this.chemicalJ, stateJ, busJ:this.busJ, packHeatJ:this.packHeatJ,
      copperJ:this.copperJ,escJ:this.escJ,frictionJ:this.frictionJ,rotorJ:this.rotorJ,
      energyError:stateJ-this.packHeatJ-this.copperJ-this.escJ-this.frictionJ-this.rotorJ,
      sourceError:stateJ-this.chemicalJ,
      chargeError:(INITIAL_SOC-this.soc)*this.model.capacityAh*3600-this.chargeC,
      thermalError:8*45*(this.temperature-298.15)-this.cellHeatJ+this.coolingJ };
  }
  hover(mass=this.model.mass) {
    let lo=0,hi=1;
    for(let i=0;i<36;i++) {
      const m=(lo+hi)/2;
      if(this.evaluate([m,m,m,m]).thrust.reduce((s,t)=>s+t,0)<mass*9.80665) lo=m; else hi=m;
    }
    return (lo+hi)/2;
  }
}
