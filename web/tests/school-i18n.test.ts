import {it,expect} from 'vitest';import {readFileSync} from 'node:fs';import {translate} from '../src/ui/i18n';
it('G12 source feedback and lesson UI are bilingual with preserved timing',()=>{
 const source=readFileSync(new URL('../src/game/school.ts',import.meta.url),'utf8');const copy=[...source.matchAll(/(?:feedback=|\?)'([^']+)'/g)].map(x=>x[1]).filter(x=>x.includes(' '));
 for(const s of [...copy,'Flight school','Retry school','Safe stop','Return to free flight','Lessons 2 / 5 · Hover 1.25 / 3.00 s']){expect(translate(s,'zh-TW')).not.toBe(s);expect(translate(s,'en')).toBe(s);}
 expect(translate('Lessons 2 / 5 · Hover 1.25 / 3.00 s','zh-TW')).toContain('1.25 / 3.00');
});
