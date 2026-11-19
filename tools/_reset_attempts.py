import sqlite3

c = sqlite3.connect(r"D:\fengge-rag\data\state.db")
c.execute(
    "UPDATE clips SET attempts = 0, last_error = NULL "
    "WHERE last_error LIKE '%WinError 2%'"
)
c.commit()
print("reset rows:", c.total_changes)
print(
    "discovered with attempts>0:",
    c.execute(
        "SELECT COUNT(*) FROM clips WHERE state='discovered' AND attempts>0"
    ).fetchone()[0],
)
