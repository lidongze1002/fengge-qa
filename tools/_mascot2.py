from pathlib import Path

NEW_SVG = """<svg viewBox="0 0 200 300" width="146" height="219" role="img" aria-label="看板娘">
    <defs>
      <linearGradient id="hairG" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#2b2d3a"/>
        <stop offset="60%" stop-color="#1d1f29"/>
        <stop offset="100%" stop-color="#15161d"/>
      </linearGradient>
      <linearGradient id="skinG" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#fff0e6"/>
        <stop offset="100%" stop-color="#ffdfd0"/>
      </linearGradient>
    </defs>
    <g stroke="#ffffff" stroke-width="5" stroke-linejoin="round" stroke-linecap="round" paint-order="stroke">
      <!-- 黑直长：后发 -->
      <path d="M100 26c-38 0-62 26-62 74v200h30V126c0-20 14-32 32-32s32 12 32 32v174h30V100c0-48-24-74-62-74z" fill="url(#hairG)"/>
      <!-- 脖子 -->
      <path d="M90 140h20v26H90z" fill="url(#skinG)" stroke="none"/>
      <!-- 身体 -->
      <path d="M44 300c0-58 24-96 56-96s56 38 56 96z" fill="#f4f6fa"/>
      <path d="M100 204l-16 12 16 14 16-14z" fill="#ffffff" stroke="none"/>
      <!-- 领结 -->
      <path d="M100 214l-14 8 14 9 14-9z" fill="#e8658d" stroke="none"/>
      <!-- 脸 -->
      <ellipse cx="100" cy="110" rx="44" ry="48" fill="url(#skinG)"/>
      <!-- 齐刘海 -->
      <path d="M54 108c0-42 20-68 46-68s46 26 46 68V84q-24-12-46-4-22-8-46 4z" fill="url(#hairG)" stroke="none"/>
      <!-- 两侧发绺 -->
      <path d="M54 86c-5 34-5 62-2 88l14-2c-4-30-4-56 0-82z" fill="url(#hairG)" stroke="none"/>
      <path d="M146 86c5 34 5 62 2 88l-14-2c4-30 4-56 0-82z" fill="url(#hairG)" stroke="none"/>
      <!-- 发丝高光 -->
      <path d="M70 62c8-10 19-16 30-18" stroke="rgba(255,255,255,.30)" stroke-width="7" fill="none"/>
      <!-- 眼睛 -->
      <ellipse cx="82" cy="116" rx="9.5" ry="12.5" fill="#2a2233" stroke="none"/>
      <ellipse cx="118" cy="116" rx="9.5" ry="12.5" fill="#2a2233" stroke="none"/>
      <circle cx="78.5" cy="111" r="3.8" fill="#fff" stroke="none"/>
      <circle cx="114.5" cy="111" r="3.8" fill="#fff" stroke="none"/>
      <circle cx="85" cy="121" r="1.9" fill="#fff" opacity=".85" stroke="none"/>
      <circle cx="121" cy="121" r="1.9" fill="#fff" opacity=".85" stroke="none"/>
      <!-- 睫毛 -->
      <path d="M71 106q11-9 22 0" stroke="#1a141f" stroke-width="4.5" fill="none"/>
      <path d="M107 106q11-9 22 0" stroke="#1a141f" stroke-width="4.5" fill="none"/>
      <!-- 眉 -->
      <path d="M73 92q9-4 17-1" stroke="#2a2233" stroke-width="2.6" fill="none" opacity=".75"/>
      <path d="M110 91q8-3 17 1" stroke="#2a2233" stroke-width="2.6" fill="none" opacity=".75"/>
      <!-- 鼻 / 嘴 -->
      <path d="M98 128q2 2 4 0" stroke="#d9a08f" stroke-width="2.4" fill="none"/>
      <path d="M94 136q6 6 12 0" stroke="#c2506b" stroke-width="3" fill="none"/>
      <!-- 腮红 -->
      <ellipse cx="67" cy="130" rx="8.5" ry="4.5" fill="#e8658d" opacity=".30" stroke="none"/>
      <ellipse cx="133" cy="130" rx="8.5" ry="4.5" fill="#e8658d" opacity=".30" stroke="none"/>
      <!-- 发夹 -->
      <path d="M128 66l12-5 4 11z" fill="#ffd166" stroke="none"/>
    </g>
  </svg>"""

p = Path(r"D:\fengge-rag\web\index.html")
s = p.read_text(encoding="utf-8")
start = s.index("<svg viewBox=\"0 0 200 240\"")
end = s.index("</svg>", start) + len("</svg>")
s = s[:start] + NEW_SVG + s[end:]

copies = [
    ("先把问题抽象成通用问题，再去比对峰哥说过的 ",
     "改写后比对 "),
    ("相似度低于阈值的会直接说没聊过，不硬凑", "没有就直说"),
    ("检索的是峰哥<strong>回答过的问题</b>，不是让 AI 替他说话。",
     "内容来自公开切片，仅作研究使用。"),
    ("数据来自 B 站 UP 主「卡秃噜皮君」的公开直播切片，仅个人研究用途，每条结果保留原视频链接。",
     "来源：B 站「卡秃噜皮君」公开切片。"),
    ("我理解成", "改写为"),
    ("<span class=\"verdict\">", "<span class=\"verdict\">"),
]
for old, new in copies:
    s = s.replace(old, new)

p.write_text(s, encoding="utf-8")
print("ok")
