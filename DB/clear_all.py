import sqlite3

def clear_all_tables(cursor):
    """Deletes all records from all tables (except "projects"), resets AUTOINCREMENT counters"""
    cursor.execute("PRAGMA foreign_keys = OFF")

    tables = ["answers", "questions", "participants", "projects"]
    for table in tables:
        cursor.execute(f"DELETE FROM {table}")
        cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = '{table}'")

    cursor.execute("PRAGMA foreign_keys = ON")
    print("All tables cleared.")

with sqlite3.connect("oedb_baseline.db") as conn:
    cursor = conn.cursor()
    clear_all_tables(cursor)