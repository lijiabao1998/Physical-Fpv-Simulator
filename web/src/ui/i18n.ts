export type Language='zh-TW'|'en';
export const LANGUAGE_KEY='physical-fpv-ui-lang-v1';
export function resolveLanguage(storage?:Pick<Storage,'getItem'>,languages:readonly string[]=[]):Language{try{const saved=storage?.getItem(LANGUAGE_KEY);if(saved==='en'||saved==='zh-TW')return saved;}catch{}return languages[0]?.toLowerCase().startsWith('zh')?'zh-TW':'en';}
export function saveLanguage(language:Language,storage?:Pick<Storage,'setItem'>){try{if(!storage)return false;storage.setItem(LANGUAGE_KEY,language);return true;}catch{return false;}}
const entries=`Physical FPV · Training Field|Physical FPV · 飛行訓練場
None|無
ESC duty|ESC 占空比
airspeed|空速
synthetic SOC|合成電池荷電狀態（SOC）
rotor speed|轉子轉速
synthetic cell temperature|合成電芯溫度
throttle|油門
roll|橫滾
pitch|俯仰
yaw|偏航
rate|角速度
dt|時間步長（dt）
Language|語言
Language / 語言|語言 / Language
Language saved on this device.|語言已儲存在此裝置。
Local storage unavailable; language applies for this visit.|無法使用本機儲存空間；語言僅套用於本次使用。
3D FPV training field|3D FPV 飛行訓練場
Game menus|遊戲選單
Aircraft|機體設定
Controls|操控設定
Physics|物理模型
Pause|暫停
Resume|繼續
Course progress|訓練進度
THE TRAINING FIELD|飛行訓練場
Five gates. One line.|五道關卡，一條飛行路線。
Your first lap starts at Gate 1|通過第 1 道關卡開始計時
KEYBOARD|鍵盤
WELCOME TO THE FLIGHT CLUB|歡迎來到飛行俱樂部
Find your line.|掌握飛行路線，
Feel the physics.|感受物理操控。
A small quad. An open field. Five gates to make your own. Build your trainer, check your controls, and take to the sky.|一架四軸飛行器、一片開闊場地、五道等待挑戰的關卡。組裝練習機、檢查操控設定，準備起飛。
Enter the field →|進入飛行訓練場 →
Physics-based flight simulation · Synthetic parameters · Not hardware validated|基於物理方程的飛行模擬 · 採用合成參數 · 尚未通過真實飛行器驗證
Loading the flight model…|正在載入飛行模型…
Preparing your trainer…|正在準備練習機…
Flight instruments|飛行儀表
THROTTLE|油門
SPEED|速度
ALTITUDE|高度
FLIGHT TIME|飛行時間
BATTERY|電池
MODE|飛行模式
Hold ARM · 0.6s|按住 ARM 解鎖 0.6 秒
ARMED|已解鎖（ARMED）
Disarm|鎖定馬達（DISARM）
Retry|重試
FPV view|第一人稱視角（FPV）
Chase view|跟隨視角
Switch to Acro|切換至 Acro（角速度操控）
Switch to Angle|切換至 Angle（姿態自穩）
Virtual flight controls|虛擬飛行操控
Yaw and integrated throttle|偏航與累積式油門
Roll and pitch|橫滾與俯仰
YAW / THROTTLE|偏航／油門
ROLL / PITCH|橫滾／俯仰
Settings|設定
Close settings|關閉設定
Saved on this device.|已儲存在此裝置。
Local storage unavailable; settings apply for this visit.|無法使用本機儲存空間；設定僅套用於本次使用。
Make it feel right|調整適合你的操控
Xbox / DualSense: Standard Gamepad Mapping, Beta. USB and Bluetooth depend on browser/OS. Physical hardware acceptance is not yet performed. Press a controller button to activate it.|Xbox／DualSense：標準手把映射，Beta 測試支援。USB 與藍牙支援取決於瀏覽器及作業系統。尚未完成實體硬體驗收。請按下手把任一按鈕以啟用。
Layout|操控配置
Console Easy · RT/R2 throttle|Console Easy（簡易手把）· RT/R2 油門
FPV Mode 2 · left stick throttle|FPV Mode 2 · 左搖桿油門
Mode 2 throttle|Mode 2 油門模式
Spring-centered: integrate up/down|彈簧置中：向上／向下累積調整
Absolute: bottom = zero, center = 50%|絕對位置：最下方 = 零，中心 = 50%
Absolute throttle needs the stick held fully down before ARM. Integrated throttle stays at its last value when centered. Disconnect or focus loss always clears throttle.|絕對位置油門必須將搖桿保持在最下方，才能 ARM 解鎖。累積式油門在搖桿置中後會維持最後數值。手把斷線或視窗失焦時，一律清除油門。
Deadzone|死區（Deadzone）
Expo|指數曲線（Expo）
Maximum rate · rad/s|最大角速度 · rad/s
FPV field of view|FPV 視野角度
Capture stick centers|校準搖桿中心點
Reset settings|重設設定
Release both sticks before capturing centers. Move each stick to both ends and enter observed min/max below. Calibrate before flying.|校準中心點前請放開兩支搖桿。將每支搖桿移至兩端，並在下方輸入觀察到的最小／最大值。請在起飛前完成校準。
ROLL|橫滾
PITCH|俯仰
YAW|偏航
Axis|軸（Axis）
Center|中心點
Min|最小值
Max|最大值
Invert|反向
Graphics quality|畫面品質
Auto · reduce shadows below 35 FPS|自動 · 低於 35 FPS 時降低陰影
High|高
Low · no shadows|低 · 關閉陰影
Procedural motor sound (optional)|合成馬達音效（選用）
Quick controls|快速操控說明
Keyboard: ↑/↓ throttle · W/S pitch · A/D roll · Q/E yaw · hold Space 0.6s ARM · X disarm · C camera · P pause · R retry · M mode.|鍵盤：↑/↓ 油門 · W/S 俯仰 · A/D 橫滾 · Q/E 偏航 · 按住空白鍵 0.6 秒 ARM 解鎖 · X 鎖定馬達 · C 視角 · P 暫停 · R 重試 · M 飛行模式。
Console: hold A/✕ 0.6s ARM · B/○ disarm · Y/△ camera · Menu/Options pause · View/Create retry. Right stick roll/pitch, left stick yaw.|手把：按住 A/✕ 0.6 秒 ARM 解鎖 · B/○ 鎖定馬達 · Y/△ 視角 · Menu/Options 暫停 · View/Create 重試。右搖桿橫滾／俯仰，左搖桿偏航。
Touch: left stick yaw and integrated throttle; right stick pitch/roll. Hold ARM to confirm. Releasing a stick centers that axis, not accumulated throttle.|觸控：左搖桿控制偏航與累積式油門；右搖桿控制俯仰／橫滾。按住 ARM 確認解鎖。放開搖桿會將該軸置中，但不會清除累積油門。
Connect a standard controller first.|請先連接標準映射手把。
Your four-rotor trainer|你的四軸練習機
Four fixed mounts. Every selection changes the synthetic physical model, not just the look.|四個固定馬達座。每個選項都會改變合成物理模型，而不只是外觀。
FRAME|機架
MOTOR|馬達
PROPELLER|螺旋槳
trainer|練習型
light|輕量型
standard|標準型
endurance|續航型
balanced|均衡型
torque|扭力型
5inch|5 吋
4inch|4 吋
Training activity|訓練活動
Five-gate course|五道關卡訓練
Free flight|自由飛行
Apply & restart|套用並重新開始
Applies a fresh synthetic pack and resets this flight. Parts are not real product ratings. Mount radius: 0.12 m; one box collision hull approximates the complete aircraft.|套用全新的合成電池組並重設本次飛行。零件參數並非真實產品規格。馬達座半徑：0.12 m；整架飛行器以單一箱形碰撞外殼近似。
Honest about the model|模型說明與限制
Newton–Euler forces and moments, a single Rapier rigid-body state, quaternion attitude, 240 Hz fixed steps. Battery voltage sag, resistive heating, motor/ESC load and static propeller thrust are calculated locally.|採用 Newton–Euler 力與力矩、單一 Rapier 剛體狀態、四元數姿態及 240 Hz 固定步長。在本機計算電池壓降、電阻發熱、馬達／ESC 負載及靜態螺旋槳推力。
Synthetic 4S2P battery and component/control coefficients. G08 adds synthetic motor/prop inertia, bounded electrical substeps, rotor kinetic energy and one-quadrant current limiting. G07 remains selectable. Static propellers omit real inflow, aerodynamic stall and propwash; no hardware calibration, regenerative braking or winding inductance. Simple box hull/obstacles, trunk colliders and passive contact impulses; foliage and distant scenery are decorative. Crash threshold is a game rule, not structural material failure. Browser/API tests are not physical-controller or real-aircraft validation.|採用合成 4S2P 電池及零件／控制係數。G08 加入合成馬達／槳葉慣量、有界電氣子步長、轉子動能及單象限限流；仍可選擇 G07。靜態螺旋槳模型未包含真實入流、氣動失速及槳流干擾；未做硬體校準，亦未模擬再生煞車或繞組電感。使用簡化箱形機體／障礙物、樹幹碰撞體及被動接觸衝量；樹葉與遠景僅為裝飾。墜機門檻是遊戲規則，不代表結構材料破壞。瀏覽器／API 測試不等於實體控制器或真實飛行器驗證。
Physics version|物理模型版本
G08 · synthetic motor transients|G08 · 合成馬達暫態
G07 · legacy quasi-steady|G07 · 舊版準穩態
Apply physics & restart flight|套用物理模型並重啟飛行
Switching resets this flight. G07 and G08 local best times remain separate. Replay exports identify their physics model.|切換會重設本次飛行。G07 與 G08 的本機最佳時間各自獨立。匯出的重播會標示物理模型。
Enable local performance diagnostics (optional)|啟用本機效能診斷（選用）
Diagnostics off|診斷已關閉
Input replay|輸入重播
Replay stores fixed-step inputs and assembly locally in an exported JSON file. Use the same build/runtime; cross-platform bitwise determinism is not promised.|重播會將固定步長的輸入與機體組合儲存在本機匯出的 JSON 檔。請使用相同建置版本／執行環境；不保證跨平台逐位元完全一致。
Choose replay file…|選擇重播檔案…
No file selected|尚未選擇檔案
Export replay|匯出重播
Watch this flight|觀看本次飛行
Import replay (maximum 32 MB)|匯入重播（最大 32 MB）
Source, evidence & limitations|原始碼、證據與限制
Replay exceeds 32 MB.|重播超過 32 MB。
Build mismatch: use an export from this build for reproducible playback.|建置版本不符：請使用此建置版本匯出的檔案，以重現播放。
Throttle to zero. Hold ARM to confirm.|請將油門歸零，按住 ARM 確認解鎖。
Ready. Zero throttle, then hold ARM.|準備就緒。油門歸零後，按住 ARM 解鎖。
ARM blocked: lower throttle to zero.|無法 ARM 解鎖：請將油門降至零。
Battery depleted. Retry for a fresh synthetic pack.|電量耗盡。請重試以換上新的合成電池組。
Armed. Raise throttle gently.|馬達已解鎖，請輕推油門。
Disarmed|馬達已鎖定
Paused and disarmed. Resume, then ARM again.|已暫停並鎖定馬達。繼續後請重新 ARM 解鎖。
Resumed, disarmed. Hold ARM with zero throttle.|已繼續，馬達仍鎖定。油門歸零後按住 ARM 解鎖。
Fresh pack. Zero throttle, then hold ARM.|已換上新電池組。油門歸零後按住 ARM 解鎖。
Replay finished. Retry to fly.|重播結束。請重試以再次飛行。
Ten-minute recording limit. Export replay and retry.|已達十分鐘錄製上限。請匯出重播並重試。
Course complete. Best time saved locally when storage is available.|訓練完成。若本機儲存可用，最佳時間將儲存在此裝置。
Synthetic pack depleted — stopped and disarmed. Retry.|合成電池組電量耗盡，已停止並鎖定馬達。請重試。
Training boundary reached — paused. Retry.|已到達訓練邊界，飛行暫停。請重試。
Input replay — same build/runtime only; no hardware claim.|輸入重播：僅限相同建置版本／執行環境；不代表硬體驗證。
Mode changed. Zero throttle, then ARM again.|模式已切換。油門歸零後請重新 ARM 解鎖。
Settings opened — paused and disarmed. Close and resume to fly.|設定已開啟：已暫停並鎖定馬達。關閉並繼續後才能飛行。
Touch interrupted — paused and disarmed.|觸控中斷：已暫停並鎖定馬達。
Touch capture lost — paused and disarmed.|觸控捕捉遺失：已暫停並鎖定馬達。
Window lost focus — paused and disarmed.|視窗失去焦點：已暫停並鎖定馬達。
Page hidden — paused and disarmed.|頁面已隱藏：已暫停並鎖定馬達。
Controller disconnected — paused and disarmed.|手把已斷線：已暫停並鎖定馬達。
Graphics context lost. Reload to restore renderer.|圖形環境遺失。請重新載入以恢復繪圖。
Frame interruption over 250 ms — paused and disarmed.|畫面中斷超過 250 ms：已暫停並鎖定馬達。
Invalid physics clock — paused and disarmed.|物理時鐘無效：已暫停並鎖定馬達。
Physics catch-up limit — paused and disarmed.|物理步數追趕達上限：已暫停並鎖定馬達。
Controller replaced — stopped and disarmed|手把已更換：已停止並鎖定馬達
Controller disconnected — stopped and disarmed|手把已斷線：已停止並鎖定馬達
Controller connected — release ARM and zero throttle, then hold ARM for 0.6 s|手把已連接：請放開 ARM 並將油門歸零，再按住 ARM 0.6 s 解鎖
Unsupported mapping — use a standard-mapped controller or keyboard|不支援此映射：請使用標準映射手把或鍵盤
Invalid controller data — disarmed|手把資料無效：馬達已鎖定
Calibration axis unavailable — disarmed|校準軸無法使用：馬達已鎖定
Your lap starts at Gate 1|通過第 1 道關卡開始計時
No best lap yet|尚無最佳單圈紀錄
Keyboard|鍵盤
Touch controls|觸控操控
TOUCH|觸控
CONTROLLER · BETA · zero throttle, release A/✕ then hold 0.6s|手把 · BETA · 油門歸零，放開 A/✕ 後再按住 0.6 秒
UNSUPPORTED PAD|不支援的手把
Unsupported or oversized replay|不支援此重播或檔案過大
Unknown physics model|未知物理模型
Invalid replay event|重播事件無效
Unknown assembly part|未知機體零件
Invalid rotor loads|轉子負載無效
Invalid rotor reaction|轉子反作用力矩無效
Invalid rotor momentum|轉子動量無效
Flight left numerical envelope|飛行已超出數值有效範圍
Exactly four duties required|必須提供四組占空比
Circuit root did not converge|電路求根未收斂
Synthetic motor/current domain exceeded|超出合成馬達／電流有效範圍
SOC midpoint did not converge|SOC 中點未收斂
Invalid quaternion|四元數無效
Invalid flight mode|飛行模式無效
Physical FPV could not start.|Physical FPV 無法啟動。
This game requires WebGL2 and WebAssembly.|此遊戲需要 WebGL2 與 WebAssembly。
No flight state was sent to a server. Reload after checking browser graphics support.|未傳送任何飛行狀態至伺服器。請檢查瀏覽器的圖形支援後重新載入。
Renderer may be masked; hardware/software status not inferred.|繪圖器資訊可能已遮蔽；不能據此判定硬體／軟體狀態。
Render CPU timing excludes asynchronous GPU work.|CPU 繪圖計時不包含非同步 GPU 工作。`;
export const dictionary:Record<string,string>=Object.fromEntries(entries.split('\n').map(line=>line.split('|')));
export function translate(source:string,language:Language):string{
 if(language==='en')return source;
 if(dictionary[source]!==undefined)return dictionary[source];
 if(source.includes('\n'))return source.split('\n').map(line=>translate(line,language)).join('\n');
 const jsonLine=source.match(/^(\s*)"([^"\n]+)": (.*)$/);
 if(jsonLine){const labels:Record<string,string>={chemicalJ:'化學能 J',stateJ:'狀態能量 J',busJ:'匯流排能量 J',packHeatJ:'電池組熱量 J',copperJ:'銅損 J',escJ:'ESC 熱量 J',frictionJ:'摩擦能量 J',rotorJ:'轉子輸出能量 J',energyError:'能量誤差 J',sourceError:'來源能量誤差 J',chargeError:'電荷誤差 C',thermalError:'熱量誤差 J',physicsModel:'物理模型',syntheticParameters:'合成參數',rotorKineticJ:'轉子動能 J',enabled:'已啟用',samples:'樣本數',fps:'FPS',frameMs:'畫面間隔 ms',physicsStepMs:'物理步耗時 ms',renderCpuMs:'CPU 繪圖耗時 ms',lastSteps:'上次步數',maxSteps:'最大步數',lastStop:'上次停止原因'};const label=labels[jsonLine[2]];if(label){let value=jsonLine[3];if(jsonLine[2]==='lastStop'){const match=value.match(/^"(.*)"(,?)$/);if(match)value='"'+translate(match[1],language)+'"'+match[2];}return jsonLine[1]+'"'+label+' ('+jsonLine[2]+')": '+value;}}
 const rules:Array<[RegExp,(...v:string[])=>string]>=[
 [/^Selected file: (.*)$/,v=>`已選擇檔案：${v}`],
 [/^TRAINING FIELD \/ v(.+)$/,v=>`飛行訓練場 / v${v}`],
 [/^(\d+) \/ 5 gates$/,v=>`${v} / 5 道關卡`],[/^Lap (.+) s$/,v=>`單圈 ${v} s`],[/^LOCAL BEST (.+) s$/,v=>`本機最佳 ${v} s`],
 [/^Impact at (.+) m\/s\. Retry to fly again\.$/,v=>`以 ${v} m/s 撞擊。請重試以再次飛行。`],
 [/^Physics guard: (.+)\. Retry\.$/,v=>`物理安全保護：${translate(v,language)}。請重試。`],[/^Invalid replay: (.+)$/,v=>`無效重播：${translate(v,language)}`],
 [/^(.+) · (Ready \(API\)|Unsupported mapping) · (keyboard|gamepad|touch)$/, (device,status,input)=>`${translate(device,language)} · ${status==='Ready (API)'?'就緒（API）':'不支援此映射'} · ${({keyboard:'鍵盤',gamepad:'手把',touch:'觸控'} as Record<string,string>)[input]}`],
 [/^Axes: (.*)$/,v=>`軸：${v}`],[/^Buttons: (.*)$/,v=>`按鈕：${v}`],
 [/^Total mass: (.*)$/,v=>`總質量：${v}`],[/^Battery: (.*) \(synthetic\)$/,v=>`電池：${v}（合成）`],[/^Motor constant: (.*)$/,v=>`馬達常數：${v}`],[/^Prop diameter: (.*)$/,v=>`槳葉直徑：${v}`],[/^Four mounts: (.*)$/,v=>`四個馬達座：${v}`],
 [/^Physics: (.*) \(synthetic\)$/,v=>`物理模型：${v}（合成）`],[/^State: (.*) \/ (ARMED|DISARMED)$/, (v,a)=>`狀態：${({ready:'準備就緒',flying:'飛行中',paused:'已暫停',crashed:'已墜機',finished:'已完成',replay:'重播中'} as Record<string,string>)[v]??v} / ${a==='ARMED'?'已解鎖（ARMED）':'已鎖定（DISARMED）'}`],
 [/^Position m: (.*)$/,v=>`位置 m：${v}`],[/^Mass: (.*)$/,v=>`質量：${v}`],[/^Current \(last electrical substep\): (.*)$/,v=>`電流（最後電氣子步）：${v}`],[/^Thrust \(physical-step mean\), N: (.*)$/,v=>`推力（物理步平均值），N：${v}`],[/^Rendered FPS: (.*) \(this session\)$/,v=>`繪圖 FPS：${v}（本次使用）`],[/^Draw calls: (.*) \/ triangles: (.*)$/, (v,t)=>`繪圖呼叫：${v} / 三角形：${t}`],[/^Quality: (Low|High) · render scale (.*)$/, (v,scale)=>`畫面品質：${v==='Low'?'低':'高'} · 繪圖縮放 ${scale}`],[/^Target only: desktop 60 \/ mobile 30 FPS$/,()=> '僅為目標：桌面 60 / 行動裝置 30 FPS'],[/^Renderer: (.*)$/,v=>`繪圖器：${v}`],[/^Vendor: (.*)$/,v=>`廠商：${v}`],[/^Build v(.*)$/,v=>`建置版本 v${v}`],[/^(.+) outside \[(.*), (.*)\]$/, (label,low,high)=>`${translate(label,language)} 超出有效範圍 [${low}, ${high}]`],
 ];
 for(const [pattern,render] of rules){const match=source.match(pattern);if(match)return render(...match.slice(1));}
 return source;
}
