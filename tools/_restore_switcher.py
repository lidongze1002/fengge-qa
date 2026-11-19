from pathlib import Path

p = Path(r"D:\fengge-rag\web\index.html")
s = p.read_text(encoding="utf-8")

# 切换按钮样式
s = s.replace(
    "  body.l2d .mascot{bottom:266px}",
    """  body.l2d .mascot{bottom:266px}
  #l2d-switch{
    position:fixed;right:182px;bottom:8px;z-index:32;
    padding:4px 10px;border-radius:999px;font-size:11.5px;
    color:var(--muted);background:rgba(255,255,255,.78);
    border:1px solid rgba(255,255,255,.9);
    -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
    box-shadow:0 6px 18px rgba(38,48,84,.12);
  }
  #l2d-switch:hover{color:var(--pink);border-color:rgba(232,101,141,.5)}
  @media(max-width:560px){#l2d-switch{display:none}}""",
)

# 重写初始化脚本：从后端拿模型列表 + 循环切换
start = s.index("<script>\n(function initMascot(){")
end = s.index("</script>", start) + len("</script>")
new = """<script>
(async function initMascot(){
  const params = new URLSearchParams(location.search);
  const img = document.getElementById("mascot-img");

  let models = [];
  try {
    models = (await (await fetch("/api/live2d/models")).json()).models || [];
  } catch (e) { /* 没装模型就退回静态图 */ }

  const order = [...models.map(m => m.name), "fengge"];
  const pick = params.get("m") || order[0];
  const model = models.find(m => m.name === pick);

  // 切换按钮
  const btn = document.createElement("button");
  btn.id = "l2d-switch";
  btn.type = "button";
  btn.textContent = "换一个";
  btn.title = "当前：" + pick;
  btn.onclick = () => {
    const next = order[(order.indexOf(pick) + 1) % order.length];
    const url = new URL(location.href);
    url.searchParams.set("m", next);
    location.href = url.toString();
  };
  if (order.length > 1) document.body.appendChild(btn);

  if (!model) {
    // fengge 或没有可用模型：只显示静态图
    return;
  }

  if (img) img.remove();
  document.body.classList.add("l2d");

  const tag = document.createElement("script");
  tag.src = "/vendor/live2d/L2Dwidget.min.js";
  tag.onload = () => {
    window.L2Dwidget.init({
      model: { jsonPath: model.json },
      display: { position: "right", width: 170, height: 260, hOffset: 0, vOffset: 0 },
      mobile: { show: false, scale: 0.5 },
      react: { opacityDefault: 1, opacityOnHover: 1 },
      dialog: false,
      log: false
    });
  };
  document.body.appendChild(tag);
})();
</script>"""
s = s[:start] + new + s[end:]

p.write_text(s, encoding="utf-8")
print("switcher restored")
