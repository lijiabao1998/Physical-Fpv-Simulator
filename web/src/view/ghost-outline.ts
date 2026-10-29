import * as THREE from 'three';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';
import type {GhostPose} from '../game/ghost';
/** Same airframe bounds, but only true edges: 132 segments instead of 246 triangle edges. */
function outlineGeometry(){
 const parts:THREE.BufferGeometry[]=[new THREE.BoxGeometry(.15,.10,.06)];
 for(const a of [-Math.PI/4,Math.PI/4])parts.push(new THREE.BoxGeometry(.28,.022,.016).rotateZ(a));
 for(const x of [-1,1])for(const y of [-1,1])parts.push(new THREE.CylinderGeometry(.064,.064,.008,8).rotateX(Math.PI/2).translate(x*.085,y*.085,.025));
 const merged=mergeGeometries(parts,false)!,edges=new THREE.EdgesGeometry(merged,1);
 // Transfer only the position buffer, not EdgesGeometry's reference to its source mesh.
 const geometry=new THREE.BufferGeometry().setAttribute('position',edges.getAttribute('position'));
 edges.dispose();merged.dispose();parts.forEach(p=>p.dispose());return geometry;
}
/** One reusable, unlit visual object; no simulation or persistence dependency. */
export class GhostOutline extends THREE.LineSegments<THREE.BufferGeometry,THREE.LineBasicMaterial> {
 private lastPose:GhostPose|null=null;
 constructor(){
  super(outlineGeometry(),new THREE.LineBasicMaterial({color:'#007e99',transparent:true,opacity:.78,depthWrite:false,toneMapped:false}));
  this.name='PB Ghost — visual only';this.matrixAutoUpdate=false;this.frustumCulled=false;
 }
 updatePose(pose:GhostPose){
  if(pose===this.lastPose)return;
  this.position.set(...pose.position);const q=pose.quaternion;this.quaternion.set(q[1],q[2],q[3],q[0]);this.updateMatrix();this.lastPose=pose;
 }
}
