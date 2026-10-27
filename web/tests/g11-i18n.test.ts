import {it,expect} from 'vitest';
import {translate} from '../src/ui/i18n';
it('G11 PB ghost feedback is bilingual and keeps exact times',()=>{
 for(const s of ['PB Ghost: ON','PB Ghost: OFF','Replay preview · PB protected','No matching Ghost for this configuration','Gate split comparison','Gate','You','PB','PB 35.97 s · waiting at Gate 1','PB 35.97 s · chase your best','PB 35.97 s · hidden']){expect(translate(s,'zh-TW')).not.toBe(s);expect(translate(s,'en')).toBe(s);}
 expect(translate('PB 35.97 s · hidden','zh-TW')).toContain('35.97');
});
