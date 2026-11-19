from pathlib import Path

NEW_SVG = """<svg viewBox="0 0 200 240" width="156" height="187" role="img" aria-label="看板娘">
    <defs>
      <linearGradient id="dress" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#ff8fb0"/>
        <stop offset="100%" stop-color="#ef5c86"/>
      </linearGradient>
      <linearGradient id="hair" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#4a5170"/>
        <stop offset="100%" stop-color="#343a52"/>
      </linearGradient>
    </defs>
    <g stroke="#ffffff" stroke-width="7" stroke-linejoin="round" stroke-linecap="round" paint-order="stroke">
      <!-- 后发 -->
      <path d="M34 100c0-44 28-74 66-74s66 30 66 74v46c0 12-8 18-18 18H52c-10 0-18-6-18-18z" fill="url(#hair)"/>
      <!-- 脖子 -->
      <rect x="90" y="140" width="20" height="18" rx="7" fill="#ffe4d6" stroke="none"/>
      <!-- 身体 -->
      <path d="M40 240c0-40 26-64 60-64s60 24 60 64z" fill="url(#dress)"/>
      <path d="M84 176h32v10a16 16 0 0 1-32 0z" fill="#fff5f8" stroke="none"/>
      <!-- 脸 -->
      <ellipse cx="100" cy="96" rx="52" ry="50" fill="#ffe4d6"/>
      <!-- 刘海 -->
      <path d="M48 92c0-36 23-58 52-58s52 22 52 58c-9-14-20-22-31-25-7 9-14 13-21 13s-14-4-21-13c-11 3-22 11-31 25z" fill="url(#hair)" stroke="none"/>
      <!-- 高光 -->
      <path d="M70 52c6-6 14-9 22-9" stroke="rgba(255,255,255,.55)" stroke-width="5" fill="none" stroke-linecap="round"/>
      <!-- 眼睛 -->
      <ellipse cx="79" cy="99" rx="8.5" ry="11" fill="#2f3346" stroke="none"/>
      <ellipse cx="121" cy="99" rx="8.5" ry="11" fill="#2f3346" stroke="none"/>
      <circle cx="82" cy="95" r="3.4" fill="#fff" stroke="none"/>
      <circle cx="124" cy="95" r="3.4" fill="#fff" stroke="none"/>
      <path d="M70 86q8-6 16-3" stroke="#2f3346" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M114 83q8-3 16 3" stroke="#2f3346" stroke-width="3" fill="none" stroke-linecap="round"/>
      <!-- 腮红 -->
      <ellipse cx="64" cy="114" rx="9" ry="5" fill="#fb7299" opacity=".38" stroke="none"/>
      <ellipse cx="136" cy="114" rx="9" ry="5" fill="#fb7299" opacity=".38" stroke="none"/>
      <!-- 嘴 -->
      <path d="M94 118q6 7 12 0" stroke="#c2506b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <!-- 耳机 -->
      <path d="M38 84c0-40 27-66 62-66s62 26 62 66" fill="none" stroke="#fb7299" stroke-width="9"/>
      <path d="M52 34l-9-18 22 7z" fill="#fb7299"/>
      <path d="M148 34l9-18-22 7z" fill="#fb7299"/>
      <rect x="28" y="80" width="20" height="36" rx="10" fill="#fb7299"/>
      <rect x="152" y="80" width="20" height="36" rx="10" fill="#fb7299"/>
      <rect x="33" y="88" width="10" height="20" rx="5" fill="#ffd9e4" stroke="none"/>
      <rect x="157" y="88" width="10" height="20" rx="5" fill="#ffd9e4" stroke="none"/>
      <!-- 发卡 -->
      <path d="M134 44l12-7 5 12z" fill="#ffd166"/>
    </g>
  </svg>"""

p = Path(r"D:\fengge-rag\web\index.html")
s = p.read_text(encoding="utf-8")
start = s.index('<svg viewBox="0 0 200 260"')
end = s.index("</svg>", start) + len("</svg>")
s = s[:start] + NEW_SVG + s[end:]
p.write_text(s, encoding="utf-8")
print("mascot replaced")
