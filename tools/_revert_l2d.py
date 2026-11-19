from pathlib import Path

p = Path(r"D:\fengge-rag\web\index.html")
s = p.read_text(encoding="utf-8")

# 1) Live2D 模式下把看板娘容器抬高到 canvas 上方
s = s.replace(
    "  #live2dcanvas{",
    "  body.l2d .mascot{bottom:266px}\n  #live2dcanvas{",
)

# 2) 初始化：默认走 Live2D，?m=fengge 才用萌版图
start = s.index("<script>\n(function initLive2D(){")
end = s.index("</script>", start) + len("</script>")
new_init = """<script>
(function initMascot(){
  const params = new URLSearchParams(location.search);
  const pick = params.get("m") || "haru";
  const MODELS = {
    haru: "/vendor/live2d/models/haru/01/assets/haru01.model.json",
    haru2: "/vendor/live2d/models/haru/02/assets/haru02.model.json",
    shizuku: "/vendor/live2d/models/shizuku/assets/shizuku.model.json",
    koharu: "/vendor/live2d/models/koharu/assets/koharu.model.json"
  };
  const img = document.getElementById("mascot-img");

  if (pick === "fengge" || !MODELS[pick]) {
    // 萌版静态图：只保留 img，不加载 Live2D
    return;
  }

  if (img) img.remove();
  document.body.classList.add("l2d");

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
  };
  document.body.appendChild(tag);
})();
</script>"""
s = s[:start] + new_init + s[end:]

# 3) 版权：主播改成「峰哥亡命天涯」，补第三方许可
s = s.replace(
    "视频与直播内容版权归 B 站 UP 主「卡秃噜皮君」及主播本人所有。",
    "视频与直播内容版权归 B 站 UP 主「卡秃噜皮君」及主播「峰哥亡命天涯」所有。",
)
s = s.replace(
    """      索引与文字由程序自动生成，可能存在误差，以原视频为准。
      如有侵权，请联系删除。""",
    """      索引与文字由程序自动生成，可能存在误差，以原视频为准。如有侵权，请联系删除。
    </p>
    <p>
      看板娘由开源项目 live2d-widget（MIT，© stevenjoezhang）与 Live2D Cubism SDK 驱动；
      示例模型版权归 Live2D Inc. 所有，仅用于技术演示。""",
)

p.write_text(s, encoding="utf-8")
print("reverted to live2d default + license updated")
