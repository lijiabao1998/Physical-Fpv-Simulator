import {it,expect} from 'vitest';
import {translate} from '../src/ui/i18n';
it('G15 U8 the three new Ghost status lines have frozen zh-TW copy and keep the exact time',()=>{
 const lines:[string,string][]=[
  ['PB 35.97 s · hidden during flight school','個人最佳 35.97 s · 飛行學校中不顯示'],
  ['PB 35.97 s · not shown in free flight','個人最佳 35.97 s · 自由飛行時不顯示'],
  ['PB 35.97 s · no Ghost stored for this PB','個人最佳 35.97 s · 未儲存 Ghost'],
 ];
 for(const [en,zh] of lines){expect(translate(en,'zh-TW')).toBe(zh);expect(translate(en,'en')).toBe(en);}
 // G11's lines keep their translations.
 expect(translate('PB 35.97 s · hidden','zh-TW')).toBe('個人最佳 35.97 s · 已隱藏');
 expect(translate('PB 35.97 s · waiting at Gate 1','zh-TW')).toBe('個人最佳 35.97 s · 等待第 1 關');
 expect(translate('PB 35.97 s · chase your best','zh-TW')).toBe('個人最佳 35.97 s · 挑戰最佳紀錄');
});
