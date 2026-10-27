import {it,expect} from 'vitest';
import {translate} from '../src/ui/i18n';
it('G09 localizes race feedback without changing numeric evidence or identity',()=>{
 for(const [source,expected] of [
 ['No best lap for this class','此設定尚無有效最佳紀錄'],
 ['LOCAL BEST 12.34 s · this class','本機最佳 12.34 s · 此設定'],
 ['Legacy unclassified: 19.00 s (not this class)','歷史未分類紀錄：19.00 s（不屬於此設定）'],
 ['G1 0.00s (+0.00) · G2 2.34s (+2.34)','第 1 關 0.00 秒（分段 +0.00） · 第 2 關 2.34 秒（分段 +2.34）'],
 ]){expect(translate(source,'zh-TW')).toBe(expected);expect(translate(source,'en')).toBe(source);}
 expect(translate('G08 · trainer / standard / sport / standard','zh-TW')).toBe('G08 · trainer / standard / sport / standard');
});
