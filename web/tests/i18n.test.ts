import {describe,it,expect} from 'vitest';
import {dictionary,LANGUAGE_KEY,resolveLanguage,saveLanguage,translate} from '../src/ui/i18n';
import {readFileSync} from 'node:fs';
describe('FPV-I18N-01 presentation only',()=>{
 it('saved valid choice wins, primary browser Chinese uses zh-TW, invalid storage falls back',()=>{
  expect(resolveLanguage({getItem:()=> 'en'},['zh-CN'])).toBe('en');
  expect(resolveLanguage({getItem:()=> 'zh-TW'},['en'])).toBe('zh-TW');
  for(const locale of ['zh','zh-TW','zh-CN','zh-HK'])expect(resolveLanguage(undefined,[locale])).toBe('zh-TW');
  expect(resolveLanguage({getItem:()=> 'bad'},['en','zh'])).toBe('en');
  expect(resolveLanguage(undefined,[])).toBe('en');
  expect(resolveLanguage({getItem:()=>{throw Error('blocked');}},['zh-TW'])).toBe('zh-TW');
 });
 it('only writes independent language key and tolerates quota/security failures',()=>{
  const writes:string[][]=[];expect(saveLanguage('zh-TW',{setItem:(k,v)=>{writes.push([k,v]);}})).toBe(true);expect(writes).toEqual([[LANGUAGE_KEY,'zh-TW']]);
  expect(saveLanguage('en',{setItem:()=>{throw Error('quota');}})).toBe(false);expect(saveLanguage('en')).toBe(false);
 });
 it('retains English verbatim and has complete nonempty bilingual dictionary',()=>{for(const [en,zh] of Object.entries(dictionary)){expect(translate(en,'en')).toBe(en);expect(zh).toBeTruthy();expect(translate(en,'zh-TW')).toBe(zh);}});
 it('covers all static safety reasons in untouched session, input and clock modules',()=>{
  for(const path of ['game/session.ts','game/timing.ts','input/manager.ts']){
   const source=readFileSync(new URL('../src/'+path,import.meta.url),'utf8');
   const strings=[...source.matchAll(/'([^'\n]+)'/g)].map(m=>m[1]).filter(s=>/paused|disarmed|throttle|Replay|replay|controller|Controller|ARM|Synthetic pack|Training boundary|Course complete|recording limit/.test(s)&&s.includes(' ')&&!s.includes('../'));
   for(const s of strings)expect(translate(s,'zh-TW'),s).not.toBe(s);
  }
 });
 it('preserves formatted numeric evidence and units',()=>{
  for(const text of ['Lap 12.30 s','Impact at 3.7 m/s. Retry to fly again.','Total mass: 0.490 kg','Position m: -0.001, 2.345, 0.105','Current (last electrical substep): 12.345 A','Thrust (physical-step mean), N: 1.234, 2.345','Physics guard: synthetic cell temperature outside [273.15, 333.15]. Retry.'])expect(translate(text,'zh-TW').match(/-?\d+(?:\.\d+)?/g)).toEqual(text.match(/-?\d+(?:\.\d+)?/g));
 });
});
