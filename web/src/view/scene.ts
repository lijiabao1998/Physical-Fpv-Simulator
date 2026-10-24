import * as THREE from 'three';
import {renderPixelRatio} from './resolution';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import {FIELD_BOXES,GATES,TREES} from '../game/field';
import type {GameSession} from '../game/session';
import type {Settings} from '../input/settings';

const Z=new THREE.Vector3(0,0,1);
export class FlightScene {
  readonly renderer:THREE.WebGLRenderer;
  readonly scene=new THREE.Scene();
  readonly camera=new THREE.PerspectiveCamera(100,1,.025,650);
  readonly drone=new THREE.Group();
  readonly rotors:THREE.Group[]=[];
  readonly gateMeshes:THREE.Mesh[][]=[];
  private sun:THREE.DirectionalLight;
  private smoothed=new THREE.Vector3(-1.7,-.05,.8);
  private lastCamera='chase';private low=false;private autoHighAttempted=false;
  private appliedQuality:Settings['quality']|null=null;
  private highlight:THREE.Mesh;
  private clock=0;
  private materials=new Map<string,THREE.MeshStandardMaterial>();
  cameraMode:'chase'|'fpv'='chase';
  fps=0;drawCalls=0;triangles=0;
  constructor(readonly canvas:HTMLCanvasElement,readonly settings:Settings) {
    this.renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:'high-performance'});
    this.renderer.outputColorSpace=THREE.SRGBColorSpace;
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.1;
    this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    this.scene.background=new THREE.Color('#bcd8e7');this.scene.fog=new THREE.Fog('#c9dcda',65,220);
    this.camera.up.copy(Z);
    this.scene.add(new THREE.HemisphereLight('#d8eafb','#6a7952',2.2));
    this.sun=new THREE.DirectionalLight('#fff1cd',3.8);this.sun.position.set(-30,-35,65);this.sun.castShadow=true;
    this.sun.shadow.mapSize.set(2048,2048);this.sun.shadow.camera.left=-55;this.sun.shadow.camera.right=55;
    this.sun.shadow.camera.top=55;this.sun.shadow.camera.bottom=-55;this.sun.shadow.camera.far=160;
    this.sun.shadow.normalBias=.02;this.sun.shadow.bias=-.0001;this.scene.add(this.sun,this.sun.target);
    this.environment();this.batchEnvironment();this.aircraft();
    this.highlight=this.box([.035,3.6,.025],'#ffc48b',[10,0,.025]);
    // Auto starts conservatively: shader/shadow warm-up must not stall input or physics.
    // High remains available explicitly; auto promotes only after measured headroom.
    this.setQuality(settings.quality!=='high');this.resize();
  }
  private material(color:string,roughness=.9) {const key=`${color}:${roughness}`;let material=this.materials.get(key);if(!material){material=new THREE.MeshStandardMaterial({color,roughness,metalness:0});this.materials.set(key,material);}return material;}
  private mesh(geo:THREE.BufferGeometry,mat:THREE.Material,pos:number[],parent:THREE.Object3D=this.scene) {
    const mesh=new THREE.Mesh(geo,mat);mesh.position.set(pos[0],pos[1],pos[2]);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;
  }
  private box(size:number[],color:string,pos:number[],parent?:THREE.Object3D) {return this.mesh(new THREE.BoxGeometry(size[0],size[1],size[2]),this.material(color),pos,parent);}
  private cylinder(top:number,bottom:number,height:number,color:string,pos:number[],parent?:THREE.Object3D,sides=8) {
    const geometry=new THREE.CylinderGeometry(top,bottom,height,sides);geometry.rotateX(Math.PI/2);return this.mesh(geometry,this.material(color),pos,parent);
  }
  private environment() {
    const ground=this.mesh(new THREE.PlaneGeometry(500,500),this.material('#819a60'),[30,0,-.02]);ground.castShadow=false;
    // Deterministic, instanced tufts: a real mesh field rather than a grid backdrop.
    const grassGeo=new THREE.ConeGeometry(.08,.35,3);grassGeo.rotateX(Math.PI/2);grassGeo.translate(0,0,.16);
    const grass=new THREE.InstancedMesh(grassGeo,this.material('#779052'),2400);
    const obj=new THREE.Object3D();let count=0;
    for(let i=0;i<3600&&count<2400;i++) {
      const x=30+Math.sin(i*78.233)*100,y=Math.sin(i*34.419+2)*80;
      if((Math.abs(x)<6&&Math.abs(y)<4)||(x>-7&&x<5&&y>4&&y<14))continue;
      obj.position.set(x,y,0);obj.scale.setScalar(.7+(i%7)*.14);obj.rotation.z=i*1.3;obj.updateMatrix();grass.setMatrixAt(count++,obj.matrix);
    }
    grass.count=count;grass.receiveShadow=true;this.scene.add(grass);
    const pad=this.box([9,6,.025],'#565e59',[0,0,-.008]);pad.castShadow=false;
    for(const y of [-2.85,2.85])this.box([8.6,.065,.007],'#ddd7b4',[0,y,.012]);
    for(const x of [-4.3,4.3])this.box([.065,5.7,.007],'#ddd7b4',[x,0,.012]);
    for(const y of [-.45,.45])this.box([1.2,.1,.008],'#e2dec5',[0,y,.014]);
    this.box([.1,.9,.008],'#e2dec5',[0,0,.014]);
    for(let x=-3;x<5;x++)this.box([.4,.07,.006],'#b9beac',[x,0,.014]);
    for(const b of FIELD_BOXES) {
      const mesh=this.box(b.half.map(x=>2*x),b.color,b.center);
      if(b.kind==='gate') {
        mesh.material=(mesh.material as THREE.Material).clone();
        if(!this.gateMeshes[Math.floor(FIELD_BOXES.indexOf(b)/3)])this.gateMeshes[Math.floor(FIELD_BOXES.indexOf(b)/3)]=[];
        this.gateMeshes[Math.floor(FIELD_BOXES.indexOf(b)/3)].push(mesh);
        if(b.half[2]>1) {
          for(let z=.3;z<1;z+=.28)this.box([b.half[0]*2+.005,.205,.14],'#3c4943',[b.center[0],b.center[1],z]);
          this.box([.65,.6,.12],'#3a4741',[b.center[0],b.center[1],.06]);
        }
      }
      if(b.kind==='crate') {
        const edge='#c0a474';
        for(const z of [b.center[2]-b.half[2]+.08,b.center[2]+b.half[2]-.08])this.box([2*b.half[0]+.02,2*b.half[1]+.02,.09],edge,[b.center[0],b.center[1],z]);
        for(const y of [-1,1]) {const plank=this.box([Math.hypot(2*b.half[0],2*b.half[2])*.95,.035,.08],edge,[b.center[0],b.center[1]+y*(b.half[1]+.018),b.center[2]]);plank.rotation.y=-Math.atan2(b.half[2],b.half[0]);}
      }
    }
    // Hangar ribs, warm interior fittings and a readable procedural sign.
    for(let x=-5.8;x<4;x+=.38)this.box([.055,.045,3.9],'#bbbda9',[x,12.82,2]);
    for(const x of [-5.8,3.8])this.box([.2,.3,4],'#4a5550',[x,4.95,2]);
    this.box([9.6,.28,.35],'#505c55',[-1,4.95,3.9]);
    this.box([9.9,7.9,.035],'#70756a',[-1,9,.01]);
    this.box([2.8,.8,.12],'#ae9271',[-2,12,1.1]);
    for(const x of [-3.2,-.8])this.box([.08,.65,1.05],'#5b665d',[x,12,.55]);
    const signCanvas=document.createElement('canvas');signCanvas.width=768;signCanvas.height=128;
    const ctx=signCanvas.getContext('2d')!;ctx.fillStyle='#353e39';ctx.fillRect(0,0,768,128);ctx.font='600 58px sans-serif';ctx.fillStyle='#ede7d6';ctx.fillText('PHYSICAL',28,86);ctx.fillStyle='#f68b4e';ctx.fillText('FPV',360,86);ctx.font='24px monospace';ctx.fillStyle='#b2c3b2';ctx.fillText('FLIGHT CLUB',518,79);
    const texture=new THREE.CanvasTexture(signCanvas);texture.colorSpace=THREE.SRGBColorSpace;
    const sign=this.mesh(new THREE.PlaneGeometry(5,.84),new THREE.MeshStandardMaterial({map:texture}),[-1,4.77,3.35]);sign.rotation.x=Math.PI/2;
    for(const tree of TREES) {
      const [x,y]=tree.position,h=tree.height;
      this.cylinder(.15,.25,h*.7,'#675842',[x,y,h*.35]);
      for(let j=0;j<3;j++)this.cylinder(.04,h*(.22-j*.04),h*.48,['#526b48','#5f7c50','#72905b'][j],[x,y,h*(.5+j*.18)],undefined,7);
    }
    // Mountains and sky clouds are scenery outside the playable boundary.
    for(let i=0;i<19;i++) {
      const angle=i/19*Math.PI*2,r=190+(i%3)*15,h=25+(i*13)%35;
      this.cylinder(0,45,h,['#859d91','#91aaa0','#a4bbb2'][i%3],[30+Math.cos(angle)*r,Math.sin(angle)*r,h/2-.5],undefined,6);
    }
    const cloudMat=new THREE.MeshStandardMaterial({color:'#f5f1de',roughness:1,flatShading:true});
    for(let i=0;i<14;i++) {
      const group=new THREE.Group();group.position.set(-100+i*20,Math.sin(i*1.8)*95,35+(i%4)*6);
      for(let j=0;j<4;j++){const puff=this.mesh(new THREE.IcosahedronGeometry(4,1),cloudMat,[j*3,Math.sin(j)*2,j%2],group);puff.scale.set(1.6,1,.45);puff.castShadow=false;puff.receiveShadow=false;}
      this.scene.add(group);
    }
    // Course center hints stay on the ground and do not obstruct FPV vision.
    for(let i=0;i<GATES.length;i++) {
      const prev=i===0?[3,0,0]:GATES[i-1].center,cur=GATES[i].center;
      const n=Math.ceil((cur[0]-prev[0])/2);
      for(let j=1;j<n;j++){const a=j/n;this.box([.34,.09,.007],'#c6cd95',[prev[0]+(cur[0]-prev[0])*a,prev[1]+(cur[1]-prev[1])*a,.01]);}
      this.gateNumber(i);
    }
  }
  /** Static scenery is merged by material/shadow flags; interactive gates stay separate. */
  private batchEnvironment() {
    this.scene.updateMatrixWorld(true);
    const dynamic=new Set(this.gateMeshes.flat());
    const groups=new Map<string,THREE.Mesh[]>();
    this.scene.traverse(object=>{
      if(!(object instanceof THREE.Mesh)||object instanceof THREE.InstancedMesh||dynamic.has(object)||Array.isArray(object.material))return;
      const key=`${object.material.uuid}:${object.castShadow}:${object.receiveShadow}`;
      const meshes=groups.get(key)??[];meshes.push(object);groups.set(key,meshes);
    });
    for(const meshes of groups.values()) {
      if(meshes.length<2)continue;
      const geometries=meshes.map(mesh=>mesh.geometry.clone().applyMatrix4(mesh.matrixWorld));
      const merged=mergeGeometries(geometries,false);
      geometries.forEach(geometry=>geometry.dispose());
      if(!merged)continue;
      const batch=new THREE.Mesh(merged,meshes[0].material);batch.castShadow=meshes[0].castShadow;batch.receiveShadow=meshes[0].receiveShadow;
      meshes.forEach(mesh=>{mesh.removeFromParent();mesh.geometry.dispose();});this.scene.add(batch);
    }
  }
  private gateNumber(i:number) {
    const canvas=document.createElement('canvas');canvas.width=128;canvas.height=128;const c=canvas.getContext('2d')!;
    c.fillStyle='#35483d';c.fillRect(0,0,128,128);c.fillStyle='#fff0d9';c.font='bold 80px monospace';c.textAlign='center';c.fillText(String(i+1),64,92);
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
    const g=GATES[i],sign=this.mesh(new THREE.PlaneGeometry(.6,.6),new THREE.MeshStandardMaterial({map:texture,side:THREE.DoubleSide}),[g.center[0]-.13,g.center[1],g.center[2]+g.height/2+.1]);
    sign.rotation.set(Math.PI/2,-Math.PI/2,0);
  }
  private aircraft() {
    this.scene.add(this.drone);
    this.box([.145,.095,.055],'#d8d3be',[0,0,0],this.drone);
    this.box([.1,.074,.022],'#323e39',[-.013,0,.037],this.drone);
    this.box([.09,.061,.035],'#efb15c',[-.012,0,.05],this.drone);
    for(const angle of [-Math.PI/4,Math.PI/4]) {const arm=this.box([.24,.018,.012],'#323c39',[0,0,-.014],this.drone);arm.rotation.z=angle;}
    for(const [x,y] of [[1,1],[-1,1],[-1,-1],[1,-1]]) {
      const a=.12/Math.sqrt(2);
      this.cylinder(.014,.016,.028,'#202c28',[x*a,y*a,0],this.drone,12);
      this.cylinder(.004,.004,.008,'#9fa49c',[x*a,y*a,.018],this.drone,8);
      const rotor=new THREE.Group();rotor.position.set(x*a,y*a,.018);
      const blade=this.box([.127,.011,.0025],x>0?'#d5b889':'#929f9a',[0,0,0],rotor);blade.castShadow=false;
      const hub=this.cylinder(.006,.006,.005,'#303b35',[0,0,0],rotor);hub.castShadow=false;
      this.drone.add(rotor);this.rotors.push(rotor);
      this.box([.025,.012,.005],x>0?'#ff8c45':'#8cc5bc',[x*a,y*a,-.02],this.drone);
    }
    // Lens faces body +x; rotor/mount dimensions match the physics model.
    const lens=this.cylinder(.013,.013,.018,'#142b2e',[.08,0,0],this.drone,12);lens.rotation.y=Math.PI/2;
    this.cylinder(.002,.002,.08,'#303932',[-.065,0,.07],this.drone,6);
    const tip=this.mesh(new THREE.SphereGeometry(.008,8,6),this.material('#e1bb6b'),[-.065,0,.11],this.drone);tip.castShadow=false;
  }
  resize() {const w=Math.max(1,this.canvas.clientWidth),h=Math.max(1,this.canvas.clientHeight);this.renderer.setPixelRatio(renderPixelRatio(w,h,devicePixelRatio,this.low&&this.settings.quality==='auto',this.low));this.renderer.setSize(w,h,false);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();}
  setQuality(low:boolean) {
    this.appliedQuality=this.settings.quality;this.low=low;this.renderer.setPixelRatio(Math.min(devicePixelRatio,low?1:1.5));this.renderer.shadowMap.enabled=!low;this.resize();
  }
  resetCamera() {this.lastCamera='';}
  render(g:GameSession,realDt:number) {
    // Auto-low and manual Low share shadows but have different raster budgets.
    // Apply the explicit mode request even when the low boolean is unchanged.
    if(this.appliedQuality!==this.settings.quality)this.setQuality(this.settings.quality!=='high');
    this.clock+=realDt;
    const p=g.world.position,q=g.world.quaternion;
    this.drone.position.set(...p);this.drone.quaternion.set(q[1],q[2],q[3],q[0]);
    // Integrate visual rotor phase from the computed omega, including simulation pause.
    this.rotors.forEach((r,i)=>{r.rotation.z=g.rotorPhases[i];r.scale.set(g.world.model.diameter/.127,g.world.model.diameter/.127,1);});
    const quat=this.drone.quaternion;
    if(this.cameraMode==='fpv') {
      this.drone.visible=false;const eye=new THREE.Vector3(.085,0,.025).applyQuaternion(quat).add(this.drone.position);
      const forward=new THREE.Vector3(Math.cos(.18),0,Math.sin(.18)).applyQuaternion(quat);
      this.camera.position.copy(eye);this.camera.up.copy(new THREE.Vector3(0,0,1).applyQuaternion(quat));this.camera.lookAt(eye.clone().add(forward));
    } else {
      this.drone.visible=true;
      const heading=Math.atan2(2*(q[0]*q[3]+q[1]*q[2]),1-2*(q[2]*q[2]+q[3]*q[3]));
      const target=new THREE.Vector3(p[0]-1.65*Math.cos(heading),p[1]-1.65*Math.sin(heading),p[2]+.65);
      if(this.lastCamera!=='chase')this.smoothed.copy(target);else this.smoothed.lerp(target,1-Math.exp(-realDt*7));
      this.camera.position.copy(this.smoothed);this.camera.up.copy(Z);this.camera.lookAt(p[0]+2*Math.cos(heading),p[1]+2*Math.sin(heading),p[2]+.3);
    }
    this.lastCamera=this.cameraMode;
    this.camera.fov=this.cameraMode==='fpv'?this.settings.fov:72;this.camera.updateProjectionMatrix();
    this.gateMeshes.forEach((meshes,i)=>meshes.forEach(m=>(m.material as THREE.MeshStandardMaterial).color.set(i<g.course.next?'#78b997':i===g.course.next?'#f8833c':'#d9ad76')));
    this.highlight.visible=g.practice&&g.course.next<GATES.length;
    if(this.highlight.visible){const gate=GATES[g.course.next];this.highlight.position.set(gate.center[0],gate.center[1],.022);}
    this.sun.position.set(p[0]-30,p[1]-35,65);this.sun.target.position.set(p[0],p[1],0);
    this.renderer.render(this.scene,this.camera);this.drawCalls=this.renderer.info.render.calls;this.triangles=this.renderer.info.render.triangles;
    if(this.settings.quality==='low'&&!this.low)this.setQuality(true);
    if(this.settings.quality==='high'&&this.low)this.setQuality(false);
  }
  autoQuality(fps:number) {
    this.fps=fps;if(this.settings.quality!=='auto'||!Number.isFinite(fps))return;
    if(fps<35&&!this.low){this.setQuality(true);this.autoHighAttempted=true;}
    else if(fps>55&&this.low&&!this.autoHighAttempted&&this.clock>10){this.autoHighAttempted=true;this.setQuality(false);}
  }
  get qualityLabel(){return `${this.low?'Low':'High'} · render scale ${this.renderer.getPixelRatio().toFixed(2)}`;}
}
