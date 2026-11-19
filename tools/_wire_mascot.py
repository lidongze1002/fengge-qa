from pathlib import Path
from PIL import Image

# 1) 压到 640，减小体积
src = Path(r"D:\fengge-rag\web\assets\fengge-chibi.png")
im = Image.open(src).convert("RGBA")
im.thumbnail((640, 640))
im.save(src, optimize=True)
print("mascot png", src.stat().st_size // 1024, "KB", im.size)

p = Path(r"D:\fengge-rag\web\index.html")
s = p.read_text(encoding="utf-8")

# 2) 用图片替换 live2d 挂载点
s = s.replace(
    '<div class="l2d-host" id="l2d-host"></div>',
    '<img class="mascot-img" id="mascot-img" src="/assets/fengge-chibi.png" alt="">',
)

# 3) 容器与图片样式
old = """  .mascot{
    position:fixed;right:14px;bottom:266px;z-index:31;
    display:flex;justify-content:flex-end;
    pointer-events:none;max-width:calc(100vw - 32px);
  }"""
new = """  .mascot{
    position:fixed;right:16px;bottom:12px;z-index:31;
    display:flex;flex-direction:column;align-items:flex-end;gap:4px;
    pointer-events:none;max-width:calc(100vw - 32px);
  }
  .mascot-img{
    width:158px;height:auto;display:block;
    mix-blend-mode:multiply;
    filter:drop-shadow(0 10px 18px rgba(40,50,80,.16));
    animation:bob 4.6s ease-in-out infinite;
    transform-origin:50% 92%;
  }
  @keyframes bob{
    0%,100%{transform:translateY(0) rotate(-0.6deg)}
    50%{transform:translateY(-6px) rotate(0.8deg)}
  }"""
assert old in s
s = s.replace(old, new)

# 4) 气泡跟着图片走
s = s.replace("margin-bottom:0;padding:9px 12px", "margin-bottom:0;padding:9px 12px")

# 5) 窄屏缩放
s = s.replace(
    """  @media(max-width:1180px){
    .bubble{max-width:min(180px, 44vw);font-size:12px}
    .bubble::after{right:24px}
  }
  @media(max-width:760px){
    .bubble{max-width:min(150px, 42vw);padding:7px 10px;font-size:11.5px}
  }""",
    """  @media(max-width:1180px){
    .mascot-img{width:132px}
    .bubble{max-width:min(180px, 44vw);font-size:12px}
    .bubble::after{right:24px}
  }
  @media(max-width:760px){
    .mascot-img{width:112px}
    .bubble{max-width:min(150px, 42vw);padding:7px 10px;font-size:11.5px}
  }""",
)

# 6) Live2D 只在显式指定 ?m=live2d 模型时启用
old_init = s[s.index('<script src="/vendor/live2d/L2Dwidget.min.js"></script>'):]
old_init = old_init[: old_init.index("</script>", old_init.index("(function initLive2D")) + len("</script>")]
new_init = """<script>
(function initLive2D(){
  const params = new URLSearchParams(location.search);
  const pick = params.get("m");
  const MODELS = {
    haru: "/vendor/live2d/models/haru/01/assets/haru01.model.json",
    haru2: "/vendor/live2d/models/haru/02/assets/haru02.model.json",
    shizuku: "/vendor/live2d/models/shizuku/assets/shizuku.model.json",
    koharu: "/vendor/live2d/models/koharu/assets/koharu.model.json"
  };
  if (!pick || !MODELS[pick]) return;   // 默认用峰哥萌版图
  const img = document.getElementById("mascot-img");
  if (img) img.remove();
  const tag = document.createElement("script");
  tag.src = "/vendor/live2d/L2Dwidget.min.js";
  tag.onload = () => {
    window.L2Dwidget.init({
      model: { jsonPath: MODELS[pick] },
      display: { position: "right", width: 170, height: 260, hOffset: 0, vOffset: 0 },
      mobile: { show: false, scale: 0.5 },
      react: { opacityDefault: 1, opacityOnHover: 1 },
      dialog: false,
      log: false
    });
    document.querySelector(".mascot").style.bottom = "266px";
  };
  document.body.appendChild(tag);
})();
</script>"""
s = s.replace(old_init, new_init)

p.write_text(s, encoding="utf-8")
print("wired mascot")
