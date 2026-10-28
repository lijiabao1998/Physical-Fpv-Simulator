import {it,expect} from 'vitest';
import {translate} from '../src/ui/i18n';
it('G10 names, count and switching status are presentation only',()=>{
 for(const source of ['Course','Training Straight','British Slalom','Industrial Run','BRITISH SLALOM','INDUSTRIAL RUN','3 / 7 gates']){expect(translate(source,'zh-TW')).not.toBe(source);expect(translate(source,'en')).toBe(source);}
 for(const id of ['training-straight','british-slalom','industrial-run'])expect(translate(id,'zh-TW')).toBe(id);
});
