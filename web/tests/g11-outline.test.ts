import {it,expect,vi} from 'vitest';
import * as THREE from 'three';
import {readFileSync} from 'node:fs';
import {GhostOutline} from '../src/view/ghost-outline';
import type {GhostPose} from '../src/game/ghost';
it('G11 outline removes redundant triangle diagonals within segment and buffer budgets',()=>{
 const g=new GhostOutline(),p=g.geometry.getAttribute('position');
 expect(g).toBeInstanceOf(THREE.LineSegments);expect(p.count/2).toBe(132);expect(p.count/2).toBeLessThan(246);expect(p.array.byteLength).toBe(3168);expect(Object.keys(g.geometry.attributes)).toEqual(['position']);
 expect(g.material.transparent).toBe(true);expect(g.material.depthWrite).toBe(false);expect(g.castShadow).toBe(false);expect(g.receiveShadow).toBe(false);expect(Object.values(g.material).some(v=>v instanceof THREE.Texture)).toBe(false);
 g.geometry.computeBoundingBox();expect(g.geometry.boundingBox!.min.x).toBeCloseTo(-.149,6);expect(g.geometry.boundingBox!.max.z).toBeCloseTo(.03,6);g.geometry.dispose();g.material.dispose();
});
it('G11 outline reuses geometry/buffers and transform across repeated poses, with independent disposal',()=>{
 const g=new GhostOutline(),other=new GhostOutline(),geometry=g.geometry,buffer=geometry.getAttribute('position').array,pose:GhostPose={tick:4,position:[1,2,3],quaternion:[1,0,0,0]},before=JSON.stringify(pose),update=vi.spyOn(g,'updateMatrix');
 for(let i=0;i<10000;i++)g.updatePose(pose);expect(update).toHaveBeenCalledTimes(1);expect(g.geometry).toBe(geometry);expect(g.geometry.getAttribute('position').array).toBe(buffer);expect(g.matrixAutoUpdate).toBe(false);expect(g.position.toArray()).toEqual([1,2,3]);
 g.updatePose({...pose,tick:8,position:[4,5,6]});expect(update).toHaveBeenCalledTimes(2);expect(g.matrix.elements.slice(12,15)).toEqual([4,5,6]);expect(JSON.stringify(pose)).toBe(before);
 expect(other.geometry).not.toBe(geometry);expect(other.geometry.getAttribute('position').array).not.toBe(buffer);const disposed=vi.fn();geometry.addEventListener('dispose',disposed);geometry.dispose();expect(disposed).toHaveBeenCalledTimes(1);expect(other.geometry.getAttribute('position').count).toBe(264);g.material.dispose();other.geometry.dispose();other.material.dispose();
});
it('G11 outline is visual-only and full renderer disposal includes line resources',()=>{
 const source=readFileSync('src/view/ghost-outline.ts','utf8');for(const forbidden of ['Rapier','GameSession','Math.random','setTranslation','setLinvel','course.update','localStorage'])expect(source).not.toContain(forbidden);
 expect(readFileSync('src/view/scene.ts','utf8')).toContain('o instanceof THREE.LineSegments');
 const browser=readFileSync('e2e/g11.spec.ts','utf8');expect(browser).toContain('if(out.length===120)');expect(browser).toContain('test.setTimeout(120000)');
});
