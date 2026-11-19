import sqlite3
from pathlib import Path

db = Path(r"D:\fengge-rag\data\state.db")
c = sqlite3.connect(db)
print("total", c.execute("SELECT COUNT(*) FROM clips").fetchone()[0])
for row in c.execute("SELECT state, COUNT(*) FROM clips GROUP BY state ORDER BY 2 DESC"):
    print(" ", row[0], row[1])
print("durations (discovered):", c.execute(
    "SELECT MIN(duration), MAX(duration), ROUND(AVG(duration)) FROM clips WHERE state='discovered'"
).fetchone())
print("accepted <=600s:", c.execute(
    "SELECT COUNT(*) FROM clips WHERE state='accepted' AND duration<=600"
).fetchone()[0])
clips = Path(r"D:\fengge-rag\dataset\clips.jsonl")
if clips.exists():
    print("clips.jsonl lines:", sum(1 for _ in clips.open(encoding="utf-8")))
