import json
import sqlite3
from typing import Literal


class JSON2DBLoader:

    TaskName = Literal["participants", "questions", "answers"]

    def __init__(self, db_path: str, project_id: int, notegroup_id: int):
        self.db_path = db_path
        self.project_id = project_id
        self.notegroup_id = notegroup_id

    @property
    def FIXED_VALUES(self) -> dict[str, dict]:
        return {
            "participants": {
                "country_staying_in": "Netherlands",
                "notegroupID": self.notegroup_id
            },
            "questions": {
                "notegroupID": self.notegroup_id
            },
            "answers": {
                "projectID": self.project_id,
                "notegroupID": self.notegroup_id
            },
            "notegroups": {
                "projectID": self.project_id
            }
        }

    @staticmethod
    def _serialize(value):
        return json.dumps(value) if isinstance(value, (dict, list)) else value

    @staticmethod
    def _get_table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cursor.fetchall()]

    @staticmethod
    def _build_row(record: dict, columns: list[str], fixed: dict) -> tuple:
        merged = {**record, **fixed}
        return tuple(JSON2DBLoader._serialize(merged.get(col)) for col in columns)

    TaskName = Literal["participants", "questions", "answers", "1recordT"]

    def load(self, json_str: str, task: TaskName) -> None:
        """
        Parse a JSON string and insert/update records in the target table.

        Args:
            json_str:  Raw JSON string containing the task's data.
            task:      One of 'participants', 'questions', 'answers', '1recordT'.
        """
        data = json.loads(json_str)

        if task == "1recordT":
            fixed = self.FIXED_VALUES.get("notegroups", {})
            merged = {**data, **fixed}

            set_clause = ", ".join(f"{col} = ?" for col in merged)
            values = tuple(self._serialize(v) for v in merged.values())

            with sqlite3.connect(self.db_path) as conn:
                sql = f"UPDATE notegroups SET {set_clause} WHERE notegroupID = ?"
                conn.execute(sql, (*values, self.notegroup_id))
                conn.commit()
                print(f"[1recordT] Updated notegroup row for notegroupID={self.notegroup_id}.")

        else:
            records = data[task]
            fixed = self.FIXED_VALUES.get(task, {})

            with sqlite3.connect(self.db_path) as conn:
                columns = self._get_table_columns(conn, task)
                rows = [self._build_row(r, columns, fixed) for r in records]

                placeholders = ", ".join("?" * len(columns))
                col_list = ", ".join(columns)
                sql = f"INSERT OR IGNORE INTO {task} ({col_list}) VALUES ({placeholders})"

                try:
                    conn.executemany(sql, rows)
                    conn.commit()
                    count = conn.execute(f"SELECT COUNT(*) FROM {task}").fetchone()[0]
                    print(f"[{task}] Inserted {len(rows)} rows. Table now has {count} rows total.")
                except sqlite3.IntegrityError as e:
                    print(f"[{task}] IntegrityError: {e}")
                    raise
                except sqlite3.OperationalError as e:
                    print(f"[{task}] OperationalError: {e}")
                    raise