import sqlite3
conn = sqlite3.connect("oedb_baseline.db")
conn.execute("PRAGMA journal_mode=WAL")
conn.close()