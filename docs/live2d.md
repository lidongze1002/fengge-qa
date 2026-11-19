# 看板娘：live2d-widget 接入与「真 Live2D」制作路径

## 1. 用的是什么

[live2d-widget](https://github.com/stevenjoezhang/live2d-widget)（MIT License，© 2018-2021 stevenjoezhang）。
它把 Live2D Cubism SDK for Web、PIXI、模型加载器打成一个 UMD bundle，暴露一个全局 `L2Dwidget`：

```js
L2Dwidget.init({ model: { jsonPath: ".../xxx.model.json" }, display: {...} });
```

内部做的事：

1. 注入 `<canvas id="live2dcanvas">`，用 PIXI 建 WebGL 上下文；
2. 拉 `.model3.json`（或旧版 `.model.json`），按里面的 `textures` / `moc` / `physics` / `motions` 逐个加载；
3. 把 moc3 的顶点、贴图、物理、表情接进渲染循环；
4. 绑定鼠标位置到 `ParamAngleX/Y`、`ParamBodyAngleX` 等参数，做出「跟着你转」的效果。

### 我们怎么接的

| 位置 | 作用 |
|---|---|
| `web/vendor/live2d/L2Dwidget.min.js` | 主 bundle（26 KB） |
| `web/vendor/live2d/L2Dwidget.0.min.js` | 代码分割出来的 chunk（151 KB），**缺了会报 `Loading chunk 0 failed`** |
| `web/vendor/live2d/models/<name>/` | 模型本体（moc3、贴图、物理、动作） |
| `tools/_fetch_live2d.py` | 从 jsDelivr 把上面这些拉到本地，离线可用 |
| `web/index.html` | `initMascot()` 按 `?m=` 选模型；`#live2dcanvas` 用 CSS 钉死在右下角 |

模型资源不进 Git（`.gitignore` 里有 `web/vendor/`），换机器跑一次 `python tools\_fetch_live2d.py` 就恢复。

切换：`?m=fengge`（默认，AI 生成的真 moc3）、`haru`、`haru2`、`shizuku`、`koharu`（官方示例）、
`chibi`（静态萌版图）。右下角「换一个」按钮按同样顺序循环。

Cubism 3/4 模型（`.model3.json`）不走 `L2Dwidget`，改用 `pixi.min.js` +
`live2dcubismcore.min.js` + `pixi-live2d-display.min.js`（都在 `web/vendor/live2d/cubism/`）；
`initMascot()` 按扩展名自动分流。

> 注意：`L2Dwidget` 给 canvas 写的是内联 `position:absolute; left:0; top:0`，
> 必须同时覆盖 `left/top/right/bottom` 才能钉在右下角，只写 `right/bottom` 会跑到左上角。

## 2. 为什么现在不是「真峰哥」

Live2D 不是「一张图 + 动效」，而是一套**分层绑定**的模型格式：

```
分层 PSD（每个零件独立图层）
   ↓  Cubism Editor 里画网格、拉变形器、绑参数
.moc3（网格与变形数据）+ textures（贴图）+ physics3.json + motion3.json
   ↓  打包
.model3.json（入口，声明上面这些文件）
   ↓  Cubism SDK / live2d-widget 加载
浏览器里能眨眼、转头、说话
```

关键点：

- **必须分层**。眼睛、嘴、眉毛、刘海、头发、身体各自独立，否则没法单独动。
- **必须绑骨**。给每个部件建 mesh、加 deformer、把参数（`ParamEyeLOpen`、`ParamMouthOpenY`、`ParamAngleX`…）拉到关键帧上。
- **`.moc3` 不再是黑盒**：`image2live2d` 用纯 Python 直接写 moc3 二进制（`backends/live2d/moc3_binary.py`），
  所以「一张图 → 真 moc3」现在能全自动跑通，见下面第 6 节。

所以：AI 现在能出「分层 PSD + 能绑的 moc3」，但**精度是初版水平**，离画师手工绑的成品还有距离。

## 3. 做真峰哥 Live2D 的四条路

### A. 自己动手（成本最低，Cubism 免费版够用）

1. 出一张**正面、无透视、四肢分开**的立绘，导出分层 PSD；
2. 装 [Live2D Cubism Editor](https://www.live2d.com/download/cubism/)（免费版可商用年收入 <1000 万日元）；
3. 按官方教程「PSD 导入 → 自动网格 → 绑参数」走一遍，2.5 头身大概 4~8 小时；
4. 导出 `xxx.model3.json` + `xxx.moc3` + `textures/`；
5. 丢进 `web/vendor/live2d/models/fengge/`，把 `initMascot` 的 `MODELS` 加一行 `fengge: ".../fengge.model3.json"` 即可。

### B. 找画师 + 绑定师（效果最好）

淘宝/B 站有整套「Live2D 立绘 + 绑定」报价，Q 版 2.5 头身大概 300~800 元，交付就是能直接用的 `model3.json` 包。
拿到后同样丢进 `models/fengge/` 就能切换。

### C. PNGTuber（最便宜的「会动」）

[PNGTuber Plus](https://github.com/IGHORSE/PNGTuberPlus) 这类工具把一张图切成「眼开/眼闭/嘴开/嘴闭」，用摄像头或鼠标驱动。
不是真 Live2D（不能转头、没有物理），但便宜、当天能出。
我们可以把已有的 `fengge-chibi.png` 手动切几层来做这个。

### D. 半自动：AI 出图 + 手工分层

用现在的 `fengge-chibi.png` 当底稿，在 Photoshop/Krita 里把眼睛、嘴、刘海、手臂抠成独立图层，再走 A 的流程。
比从零画快，但分层质量取决于原图，眼睛被头发压住的地方要补画。

## 4. 许可与署名

| 组件 | 许可 |
|---|---|
| live2d-widget | MIT，© stevenjoezhang |
| Live2D Cubism SDK for Web | Live2D 专有许可，小规模事业者免费 |
| 示例模型（haru / shizuku / koharu） | Live2D Inc. 免费示例素材，仅限演示/学习 |
| 峰哥萌版图 | 本项目生成，形象涉及真人，仅个人研究使用 |

页脚已注明来源；如果之后接入自制的峰哥模型，需要另外确认**肖像权**（真人形象的二创和公开传播与版权是两件事）。

## 5. 现有的 AI 自动化方案（2026-11 调研）

结论先说：**「一张图 → 可用的 Live2D 初版」已经能跑通**，但产出是「待精修的初版」，
不是画师级的成品。链路统一是：

`
单张立绘
  → See-Through（AI 语义拆层，出 ~27 个部件 + 深度图）
  → 分层 PSD
  → PSD2Live（自动网格 / 变形器 / 物理 / 待机动作）
  → .moc3 + .model3.json
  → live2d-widget / VTube Studio 加载
`

### 关键项目

| 项目 | 作用 | 许可 | 备注 |
|---|---|---|---|
| [See-Through](https://github.com/shitagaki-lab/see-through) | 单图 → 语义分层 | 研究用途 | 整条链路的地基；显存杀手 |
| [tsunehimatoi/psd2live](https://github.com/tsunehimatoi/psd2live) | PSD → 自动绑定 → moc3/cmo3 | GPL-3.0 | 有 GUI、CLI、MCP；事实标准 |
| [lvhaojie456/image-to-live2d](https://github.com/lvhaojie456/image-to-live2d) | 端到端九阶段流水线 + 视觉验收 | MIT | 最完整，含 Core 姿态校验 |
| [flowingduskpro/jpg-to-live2d-workflow](https://github.com/flowingduskpro/jpg-to-live2d-workflow) | 同上，**8GB 显存实测** | - | 实测机型就是 RTX 4060 Laptop 8GB |
| [naiyouj/live2d-ai-generator](https://github.com/naiyouj/live2d-ai-generator) | 本地 Web 应用，五步可视化 | - | 8GB 分档、断点续跑、可手动接管 |
| [Wzhang3912/image2live2d](https://github.com/Wzhang3912/image2live2d) | 分层图 → 绑定 → moc3/inp | Apache-2.0 | 输出格式中立 |
| [chaosdream/live2d-auto-psd](https://github.com/chaosdream/live2d-auto-psd) | 用 Gemini/GPT 切 11 层 → PSD | - | 只做拆层，不做绑定 |
| [Ariakage/live2d-agent-kit](https://github.com/Ariakage/live2d-agent-kit) | Codex 工作流 + 示例模型 | - | 适合当模板抄流程 |
| [KonshinHaoshin/autoLive2d](https://github.com/KonshinHaoshin/autoLive2d) | MCP：PSD → 官方 moc3 | MIT | 依赖本机 Cubism 安装 |

### 能达到什么程度（各项目自述 + 实测口径）

- 能自动：网格、变形器链、角度 X/Y、眨眼、口型参数、头发物理、待机动作
- 半自动：五官精细变形、遮挡补画、表情差分
- 仍需人工：被遮挡像素的补画（闭眼时的眼皮、张嘴时的口腔）、手部与头发接缝、
  逐点精确变形（所有项目都明确说 Agent 做不好）

### 对「峰哥」这条链路的建议

1. 用现有的 web/assets/fengge-chibi.png 当母图（A-pose、纯色背景、正面全身最好）；
2. 跑 jpg-to-live2d-workflow（它就是在 4060 8GB 上调通的），产出分层 PSD + moc3；
3. 人工补画：闭眼、张嘴、后发被遮的部分（这是质量分水岭）；
4. 产物丢进 web/vendor/live2d/models/fengge/，?m=fengge 即可切换。

代价：8GB 卡跑 See-Through 大约 1 小时满载，风扇会响；之后绑定只要几分钟。

## 6. 实际跑通的链路（2026-11-18，RTX 4060 Laptop 8GB）

用的是 [naiyouj/live2d-ai-generator](https://github.com/naiyouj/live2d-ai-generator) v2
（本地 Web 控制台，`http://127.0.0.1:7800`），产物已接入 `?m=fengge`。

### 环境

| 件 | 版本 / 位置 |
|---|---|
| Python | 3.10.11（项目自带 `.venv`） |
| torch / torchvision | `2.8.0+cu128` / `0.23.0+cu128`（`download.pytorch.org`，约 3.3 GB） |
| diffusers / transformers / tokenizers / accelerate | `0.37.0` / `5.0.0` / `0.22.2` / `1.13.0`（必须按 see-through 的 pin，别用 pip 默认最新） |
| 额外依赖 | `pycocotools`（依赖清单漏了，`utils/cv.py` 会 import） |
| 分层权重 | `HF_HOME=D:\fengge-rag\live2d-build\hf-cache`，约 5.3 GB |
| 渲染库 | `pixi.min.js` 6.5.10 + `live2dcubismcore.min.js` + **`pixi-live2d-display` 的 `cubism4` 构建** |

### 命令

```powershell
cd D:\fengge-rag\live2d-build\live2d-ai-generator-main
$env:HF_ENDPOINT='https://hf-mirror.com'; $env:HF_HUB_DISABLE_XET='1'
$env:HF_HOME='D:\fengge-rag\live2d-build\hf-cache'
.\.venv\Scripts\python.exe run.py           # 控制台 127.0.0.1:7800
```

第 1 步上传 `web/assets/fengge-ref.png`（1024×1536 RGBA），第 2 步「仅裁切」，
第 3 步 NF4 / 1024 / 30 步，第 4 步绑骨，第 5 步预览导出。
整条流水线约 10 分钟（分层 8 分钟、绑骨+导出 10 秒），显存峰值 7.8/8.2 GB。

产物拷到 `web/vendor/live2d/models/fengge/`（6.9 MB，28 张贴图、24 组动作、`character.moc3`）。

### 踩过的坑

1. **`huggingface_hub` 版本**：pip 默认装 `1.7.2` 但 diffusers 0.41 要 `>=1.32`，
   且 `resolve_revision` 已被移除 → 必须回到 `diffusers==0.37.0`。
2. **`pycocotools` 缺失**：`modules/layerdiffuse/vae.py` → `utils/cv.py` 里 import。
3. **`pixi-live2d-display` 的 `index.min.js` 是「全量」构建**：加载时会去找 Cubism 2 运行时
   （`live2d.min.js`），找不到就抛异常并**中断后续导出**，`PIXI.live2d` 里只剩 `config`。
   只跑 Cubism 4 就用 `dist/cubism4.min.js`。
4. **`autoUpdate` 挂在 `PIXI.Ticker.shared`，不是 `app.ticker`**：`new PIXI.Application({sharedTicker:true})`
   或干脆 `autoUpdate=false` 自己用 `app.ticker` 驱动 `model.update(deltaMS/1000)`。
5. **`model.motion(group)` 首次调用只触发懒加载并返回 `false`**，要再调一次才真正播放。
6. **`L2Dwidget` 的 canvas 高 260、pixi 画布高 196**，气泡的 `bottom` 要分两套值
   （`body.l2d` / `body.cubism4`），否则会压住头顶。

### 已知不足

- 胡子盖住了嘴：`ParamMouthOpenY` 绑定是通的（手动置 1 会改变 2246 px），但张嘴时口腔在胡子后面，看不太出来。
- 闭眼、张嘴的「补画」层由 AI 生成，眼睑和口腔边缘不如手绘干净。
- 手臂/手指接缝在抬手动作里偶有轻微拉伸。
- 抬头到极限时脖子会显得偏长（脖子是往下垫出来的，见下面「二期修补」）。

## 7. 二期修补：脖子 / 穿模 / 脚

用户反馈三个问题：没脖子、低头穿模、没有脚。都不是渲染问题，是**分层素材本身就缺**：

| 问题 | 根因 | 处理 |
|---|---|---|
| 没脖子 | See-Through 给的 `neck` 层只有 67×60，且被下巴（y=427）和西装领口（y=404）夹在中间，露出高度是负的 | 把西装+手臂整体下移 18px，把领口那块灰色空洞涂成皮肤写进 `topwear` |
| 低头穿模 | 头一低，下巴抬起，露出的区域是**透明**的（原画里被下巴挡住的领口内侧是灰的） | 同一块皮肤补丁往上多垫 24px（梯形收窄），被下巴挡着不露，头一低就露皮肤 |
| 没有脚 | `legwear` 只到脚踝，鞋根本没被分层出来（深色鞋在暗背景上被漏掉） | 从原图 `clean.png` 腿部下方整条切出来，按左右两块拆成 `leg_l` / `leg_r` |

关键取舍：**脖子没有做成独立的 `neck` 零件**。试过了，`image2live2d` 会按语义重排 z 序
（`core/structure/zorder.py`），拆出来的 neck 会被西装盖住，渲染出来还是灰的；
直接涂进 `topwear` 反而稳。

另外把 `front hair` 提到了 `face` 之上——原来的层序是头发在下，刘海被脸皮盖掉了。

### 「脸后面是空的 / 和脖子不连接」

头是**刚性整体旋转**的：`face`、`hair`、眼睛都是平板，转到侧面时下巴会和脖子分开，
中间露出衬衫的白，看起来就是"脸后面空着、没连上"。

试过两条路，都不行：

1. **给下巴接一段皮肤（贴进 `face` 层）**：一转头这段皮肤就跟着转，从胡子旁边探出一块
   硬边矩形，像贴了张纸条。
2. **把 `neck` 做成独立零件**：`image2live2d` 的 `normalize_neck_zorder()`
   （`core/structure/zorder.py`）会**主动**把脖子压到 `face_base` 和衣服后面——
   源码注释写得很清楚：脖子压在脸上时，它那条矩形裁切边会在转头的一瞬间从下巴边上戳出来。
   所以独立 neck 永远显示不到领口前面。

最终方案：**限制转头幅度**。库里的 `updateFocus()` 写死了 `30 * focus.x`，
在前端把 focus 缩到 0.4，实际只转 ±12°：

```js
const origFocus = im.updateFocus.bind(im);
im.updateFocus = function () {
  const f = this.focusController;
  const ox = f.x, oy = f.y;
  f.x = ox * 0.4; f.y = oy * 0.4;
  try { origFocus(); } finally { f.x = ox; f.y = oy; }
};
```

±12° 下巴始终在脖子范围内，静止脖子（涂在 `topwear` 里那块）就能一直盖住。
`Head_yaw` / `Head_pitch` 这些动作本身还是 ±30，手动播的时候仍会露缝——不用就不影响。

重建脚本：`live2d-build/build_fix_psd.py`（生成 `fix-out/layers_fixed.psd`），
然后

```powershell
# 在 live2d-ai-generator-main/tools/image2live2d 下
$env:PYTHONPATH="$PWD\src"
..\..\.venv\Scripts\python.exe -m image2live2d --psd ..\..\..\fix-out\layers_fixed.psd `
  --work-dir ..\..\..\fix-out\layers -o ..\..\..\fix-out\fengge.inp `
  --name fengge --live2d ..\..\..\fix-out\live2d
```

产物拷到 `web/vendor/live2d/models/fengge/`，旧模型备份在
`web/vendor/live2d/_backup/fengge-old/`（不在切换列表里）。

复现参数：`SCALE=0.85`（整体缩小，给脖子腾空间）、`HEAD_UP=44`、`BODY_DOWN=34`
（头往上、身体往下，中间空出 60px 填脖子）；鞋子从 `preprocess/clean.png` 的
`legwear` 底边往下整条切、按列投影找左右脚之间的空隙拆开。

### 脖子怎么"长"出来的

原画里下巴直接压在衬衫领上，**没有脖子**——只在原地画一块皮肤是没用的，
因为领口到下巴只有 20px，显示到 186px 的画布上只剩 5px，等于没有。

只能动构图：

1. 整张图缩到 85%（上下腾出约 77px 余量，头发也不会被画布顶裁掉）
2. 头部（脸/五官/头发/耳朵）上移 44px，身体（西装/手臂/腿/鞋）下移 34px
3. 下巴到领口之间空出 **60px**，填一段梯形皮肤：上窄（37 半宽，藏在下巴后面）、
   下宽（54 半宽，塞进领口），顶部加下巴投影（0.66 → 1.0 渐进）

关键是脖子**顶端远高于下巴**（`NECK_TOP = chin - 46`），所以头一定盖住它一截，
露出来的永远是"中间那段脖子"，不会出现头和脖子之间的缝。

| 效果 | `HEAD_UP + BODY_DOWN` |
|---|---|
| 0（原画） | 没脖子 |
| 20 | 一条缝 |
| **78（当前）** | 显示尺寸下约 11px，能清楚看到脖子 |
| 100+ | 头会显得和身体脱节 |

18 那版试过，用户反馈"头像悬在空中"，所以收到 6。
`build_fix_psd.py` 里改一个数字就能重出，代价是 `BODY_DY` 只影响 topwear / handwear 的偏移，
改动后必须重跑 `image2live2d`。

