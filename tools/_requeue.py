import sqlite3

c = sqlite3.connect(r"D:\fengge-rag\data\state.db")
n = c.execute(
    "SELECT COUNT(*) FROM clips WHERE state='failed' AND last_error IS NULL"
).fetchone()[0]
c.execute(
    "UPDATE clips SET state='discovered', attempts=0, last_error=NULL "
    "WHERE state='failed' AND last_error IS NULL"
)
c.commit()
print("requeued", n)
print(dict(c.execute("SELECT state, COUNT(*) FROM clips GROUP BY state").fetchall()))
