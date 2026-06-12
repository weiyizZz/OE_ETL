import sqlite3

DB_PATH = "oedb_baseline_v2.db"

with sqlite3.connect(DB_PATH) as conn:
    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute("""
        DELETE FROM questions
        WHERE questionID NOT IN (SELECT DISTINCT questionID FROM answers)
          AND questionID NOT IN (
              SELECT DISTINCT followed_questionID FROM questions
              WHERE followed_questionID IS NOT NULL
          )
    """)
    conn.commit()
    print(f"Removed {conn.total_changes} questions.")