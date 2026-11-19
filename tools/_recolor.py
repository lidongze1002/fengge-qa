from pathlib import Path

p = Path(r"D:\fengge-rag\web\index.html")
s = p.read_text(encoding="utf-8")

pairs = [
    ("background:#121315", "background:rgba(255,255,255,.92)"),
    ("textarea::placeholder{color:#5f636a}", "textarea::placeholder{color:#9aa1af}"),
    (".ch:hover{color:var(--text);border-color:#4a4b52}",
     ".ch:hover{color:var(--text);border-color:rgba(251,114,153,.55)}"),
    ("padding:9px 12px;background:#101113;border-left:2px solid var(--blue);",
     "padding:9px 12px;background:rgba(10,167,224,.09);border-left:2px solid var(--blue);"),
    ("border-radius:0 4px 4px 0;font-size:13px;color:#b9c6cc;",
     "border-radius:0 4px 4px 0;font-size:13px;color:#3f4b5c;"),
    (".answer{font-size:14.5px;line-height:1.85;color:#d3d5d9;overflow-wrap:anywhere}",
     ".answer{font-size:14.5px;line-height:1.85;color:#2b2e37;overflow-wrap:anywhere}"),
    ("margin-top:12px;padding:10px 12px;background:#101113;border-radius:4px;",
     "margin-top:12px;padding:10px 12px;background:rgba(251,114,153,.10);border-radius:4px;"),
    ("font-size:13.5px;line-height:1.7;color:#e8c9d3;",
     "font-size:13.5px;line-height:1.7;color:#8e2f4d;"),
    (".rel button:hover{border-color:#4a4b52}",
     ".rel button:hover{border-color:rgba(251,114,153,.55)}"),
    (".rel .q{font-size:12px;line-height:1.45;color:#c9cbd0;",
     ".rel .q{font-size:12px;line-height:1.45;color:#3d4250;"),
    (".item:hover{border-color:#4a4b52;background:#232428}",
     ".item:hover{border-color:rgba(251,114,153,.55);background:rgba(255,255,255,.92)}"),
    (".item .q{font-size:13px;line-height:1.5;color:#d5d7db;",
     ".item .q{font-size:13px;line-height:1.5;color:#333846;"),
    (".cm{display:flex;gap:8px;padding:8px 0;border-top:1px solid #26272b;font-size:13px;line-height:1.6}",
     ".cm{display:flex;gap:8px;padding:8px 0;border-top:1px solid rgba(24,28,42,.08);font-size:13px;line-height:1.6}"),
    (".cm .c{color:#d3d5d9;word-break:break-word}",
     ".cm .c{color:#2b2e37;word-break:break-word}"),
    ("border:2px solid #3a3b40;border-top-color:var(--pink);",
     "border:2px solid rgba(24,28,42,.16);border-top-color:var(--pink);"),
    ("border:1px solid var(--line);border-radius:6px;background:#101113}",
     "border:1px solid var(--line);border-radius:6px;background:rgba(255,255,255,.9)}"),
    ("color:#c6c9ce;border-bottom:1px solid #1d1e22;",
     "color:#3a3f4c;border-bottom:1px solid rgba(24,28,42,.07);"),
    (".sk{background:linear-gradient(90deg,#1e1f23 25%,#26272c 37%,#1e1f23 63%);",
     ".sk{background:linear-gradient(90deg,rgba(255,255,255,.55) 25%,rgba(235,239,248,.95) 37%,rgba(255,255,255,.55) 63%);"),
    ('.seg:hover{background:rgba(251,114,153,.08);color:#fff}',
     '.seg:hover{background:rgba(251,114,153,.12);color:#1b1d24}'),
    ('.seg.on{background:rgba(251,114,153,.12);color:#fff}',
     '.seg.on{background:rgba(251,114,153,.18);color:#1b1d24}'),
    ('COLORS = ["251,114,153", "0,174,236", "255,176,39"]',
     'COLORS = ["251,114,153", "64,170,255", "255,178,60"]'),
    ("a: 0.15 + Math.random() * 0.45,", "a: 0.25 + Math.random() * 0.45,"),
]

missing = []
for old, new in pairs:
    if old not in s:
        missing.append(old[:50])
    s = s.replace(old, new)

p.write_text(s, encoding="utf-8")
print("applied", len(pairs) - len(missing), "of", len(pairs))
for m in missing:
    print("MISS:", m)
