import RAPIER from '@dimforge/rapier3d-compat';
import { DEFAULT_MODEL, GRAVITY, RHO, validateDt, type Model } from './config';
import { FIELD_BOXES,TREES } from '../game/field';
import { add, dot, inverseRotate, norm, normalized, rotate, scale, type Q4,type V3 } from './math';
import type { PowerOutput } from './powertrain';

let init: Promise<void> | undefined;
export function initPhysics() { return init??=RAPIER.init(); }
const vec=(v: V3)=>({x:v[0],y:v[1],z:v[2]});
const arr=(v: {x:number;y:number;z:number}): V3=>[v.x,v.y,v.z];
export class FlightWorld {
  readonly world: RAPIER.World;
  readonly body: RAPIER.RigidBody;
  readonly collider: RAPIER.Collider;
  readonly events=new RAPIER.EventQueue(true);
  contacts=0; impactSpeed=0; contact=false;
  constructor(readonly model: Model=DEFAULT_MODEL, environment=true) {
    this.world=new RAPIER.World({x:0,y:0,z:-GRAVITY});
    this.world.numSolverIterations=8;
    const desc=RAPIER.RigidBodyDesc.dynamic().setTranslation(0,0,.105).setCanSleep(false).setCcdEnabled(true)
      .setAdditionalMassProperties(model.mass,{x:0,y:0,z:0},vec(model.inertia),{x:0,y:0,z:0,w:1});
    this.body=this.world.createRigidBody(desc);
    this.collider=this.world.createCollider(RAPIER.ColliderDesc.cuboid(.14,.14,.06).setMass(0).setFriction(.6).setRestitution(0).setActiveEvents(RAPIER.ActiveEvents.COLLISION_EVENTS),this.body);
    if(environment) {
      this.world.createCollider(RAPIER.ColliderDesc.cuboid(250,250,.5).setTranslation(0,0,-.5).setFriction(.7).setRestitution(0));
      for(const box of FIELD_BOXES) this.world.createCollider(RAPIER.ColliderDesc.cuboid(...box.half).setTranslation(...box.center).setFriction(.5).setRestitution(0));
      for(const tree of TREES) this.world.createCollider(RAPIER.ColliderDesc.cuboid(.25,.25,tree.height*.35).setTranslation(tree.position[0],tree.position[1],tree.height*.35).setRestitution(0));
    }
  }
  get position() { return arr(this.body.translation()); }
  get velocity() { return arr(this.body.linvel()); }
  get quaternion(): Q4 {const q=this.body.rotation();return normalized([q.w,q.x,q.y,q.z]);}
  get rates() {return inverseRotate(this.quaternion,arr(this.body.angvel()));}
  kinetic() {const rates=this.rates;return .5*this.model.mass*dot(this.velocity,this.velocity)+.5*rates.reduce((s,w,i)=>s+this.model.inertia[i]*w*w,0);}
  /** Only reset/test fixture creation writes an initial transform; inputs apply forces. */
  setInitial(position: V3,velocity: V3=[0,0,0],quaternion: Q4=[1,0,0,0],rates: V3=[0,0,0]) {
    const [w,x,y,z]=normalized(quaternion);
    this.body.setTranslation(vec(position),true);this.body.setLinvel(vec(velocity),true);
    this.body.setRotation({w,x,y,z},true);this.body.setAngvel(vec(rotate([w,x,y,z],rates)),true);
    this.body.resetForces(true);this.body.resetTorques(true);
  }
  step(power: Pick<PowerOutput,'thrust'|'torque'> & {reactionTorque?:number[];rotorAngularMomentum?:number},dt: number,drag=true) {
    validateDt(dt);
    if(power.thrust.length!==4||power.torque.length!==4||power.thrust.some(t=>!Number.isFinite(t)||t<0||t>100)||power.torque.some(t=>!Number.isFinite(t)||t<0||t>5)) throw Error('Invalid rotor loads');
    if(power.reactionTorque && (power.reactionTorque.length!==4||power.reactionTorque.some(t=>!Number.isFinite(t)||Math.abs(t)>5)))throw Error('Invalid rotor reaction');
    if(power.rotorAngularMomentum!==undefined&&(!Number.isFinite(power.rotorAngularMomentum)||Math.abs(power.rotorAngularMomentum)>1))throw Error('Invalid rotor momentum');
    const q=this.quaternion,rates=this.rates,v=this.velocity;
    const bodyV=inverseRotate(q,v);
    const dragBody: V3=bodyV.map((x,i)=>drag?-.5*RHO*[.025,.025,.04][i]*x*Math.abs(x):0) as V3;
    const thrust=power.thrust.reduce((s,t)=>s+t,0);
    const force=rotate(q,add(dragBody,[0,0,thrust]));
    const a=this.model.arm/Math.sqrt(2),t=power.thrust,r=power.reactionTorque??power.torque;
    const moment: V3=[a*(t[0]+t[1]-t[2]-t[3]),a*(-t[0]+t[1]+t[2]-t[3]),r[0]-r[1]+r[2]-r[3]];
    // Rotor relative angular momentum: -omega_body cross H_rotor.
    const H=power.rotorAngularMomentum??0;moment[0]-=rates[1]*H;moment[1]+=rates[0]*H;
    // Rapier handles rigid-body inertia/gyroscopic integration; add only applied moments.
    const torque=rotate(q,add(moment,scale(rates,drag?-.001:0)));
    this.body.resetForces(true);this.body.resetTorques(true);
    this.body.addForce(vec(force),true);this.body.addTorque(vec(torque),true);
    this.world.timestep=dt;
    this.world.step(this.events);
    this.contact=false; this.impactSpeed=0;
    this.events.drainCollisionEvents((c1,c2,started)=>{
      if(started&&(c1===this.collider.handle||c2===this.collider.handle)) {
        this.contacts++;this.contact=true;this.impactSpeed=norm(v);
      }
    });
    if(![...this.position,...this.velocity,...this.rates].every(Number.isFinite)||norm(this.rates)>100||norm(this.velocity)>150) throw Error('Flight left numerical envelope');
  }
  dispose() { this.events.free();this.world.free(); }
}
