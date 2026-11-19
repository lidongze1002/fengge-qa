from pathlib import Path

p = Path(r"D:\fengge-rag\web\index.html")
s = p.read_text(encoding="utf-8")

# 1) 移除手绘 SVG
start = s.index('<svg viewBox="0 0 200 300"')
end = s.index("</svg>", start) + len("</svg>")
s = s[:start] + '<div class="l2d-host" id="l2d-host"></div>' + s[end:]

# 2) 看板娘容器只留气泡，位置抬到 canvas 上方
old_css = """  /* 看板娘 */
  .mascot{
    position:fixed;right:24px;bottom:10px;z-index:30;
    display:flex;flex-direction:column;align-items:flex-end;justify-content:flex-end;gap:6px;
    pointer-events:none;max-width:calc(100vw - 32px);
  }
  .mascot svg{
    width:146px;height:auto;display:block;flex:0 0 auto;
    filter:drop-shadow(0 14px 26px rgba(40,50,80,.20));
    animation:bob 4.4s ease-in-out infinite;
    transform-origin:50% 100%;
  }
  @keyframes bob{
    0%,100%{transform:translateY(0)}
    50%{transform:translateY(-7px)}
  }"""
new_css = """  /* 看板娘（Live2D canvas 由 L2Dwidget 注入，气泡单独定位） */
  .mascot{
    position:fixed;right:14px;bottom:266px;z-index:31;
    display:flex;justify-content:flex-end;
    pointer-events:none;max-width:calc(100vw - 32px);
  }
  #live2dcanvas{
    position:fixed !important;right:0 !important;bottom:0 !important;
    z-index:30 !important;pointer-events:none;
  }
  #live2d-hint{
    position:fixed;right:12px;bottom:6px;z-index:31;font-size:11px;color:var(--muted-2);
    pointer-events:auto;cursor:pointer;opacity:.6;
  }
  #live2d-hint:hover{opacity:1;color:var(--pink)}"""
assert old_css in s
s = s.replace(old_css, new_css)

# 3) 窄屏适配：气泡随 canvas 一起缩小
s = s.replace(
    """  @media(max-width:1180px){
    .mascot{right:14px;bottom:8px}
    .mascot svg{width:112px}
    .bubble{max-width:min(180px, 44vw);font-size:12px}
    .bubble::after{right:24px}
  }
  @media(max-width:760px){
    .bubble{max-width:min(150px, 42vw);padding:7px 10px;font-size:11.5px}
    .mascot svg{width:96px}
  }
  @media(max-width:560px){.mascot{display:none}}""",
    """  @media(max-width:1180px){
    .mascot{bottom:220px}
    .bubble{max-width:min(180px, 44vw);font-size:12px}
    .bubble::after{right:24px}
  }
  @media(max-width:760px){
    .mascot{bottom:180px}
    .bubble{max-width:min(150px, 42vw);padding:7px 10px;font-size:11.5px}
  }
  @media(max-width:560px){.mascot,#live2dcanvas,#live2d-hint{display:none}}""",
)

# 4) 注入 Live2D 初始化脚本
init = """
<script src="/vendor/live2d/L2Dwidget.min.js"></script>
<script>
(function initLive2D(){
  if (!window.L2Dwidget) return;
  const params = new URLSearchParams(location.search);
  const pick = params.get("m") || "haru";
  const MODELS = {
    haru: "/vendor/live2d/models/haru/01/assets/haru01.model.json",
    haru2: "/vendor/live2d/models/haru/02/assets/haru02.model.json",
    shizuku: "/vendor/live2d/models/shizuku/assets/shizuku.model.json",
    koharu: "/vendor/live2d/models/koharu/assets/koharu.model.json"
  };
  const jsonPath = MODELS[pick] || MODELS.haru;
  window.L2Dwidget.init({
    model: { jsonPath },
    display: { position: "right", width: 170, height: 260, hOffset: 0, vOffset: 0 },
    mobile: { show: false, scale: 0.5 },
    react: { opacityDefault: 1, opacityOnHover: 1 },
    dialog: false,
    log: false
  });
  const hint = document.createElement("div");
  hint.id = "live2d-hint";
  hint.textContent = "换一个";
  hint.title = "切换模型：?m=haru / haru2 / shizuku / koharu";
  hint.onclick = () => {
    const order = ["haru", "haru2", "shizuku", "koharu"];
    const next = order[(order.indexOf(pick) + 1) % order.length];
    const url = new URL(location.href);
    url.searchParams.set("m", next);
    location.href = url.toString();
  };
  document.body.appendChild(hint);
})();
</script>
</body>"""
s = s.replace("</body>", init, 1)

p.write_text(s, encoding="utf-8")
print("live2d wired")
