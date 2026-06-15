import sqlite3
import json


class DB2jsonTest:

    PK_COLUMNS = {
        "participants": "participantID",
        "questions": "questionID",
        "answers": "answerID",
        "notegroups": "notegroupID",
    }

    def __init__(self, db_path: str, table_name: str, primary_key: int):
        self.db_path = db_path
        self.table_name = table_name
        self.primary_key = primary_key

    # ── fetch helpers ────────────────────────────────────────────────────

    def _fetch_record(self, table: str, pk_value: int) -> dict:
        pk_col = self.PK_COLUMNS[table]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"SELECT * FROM {table} WHERE {pk_col} = ?", (pk_value,))
            columns = [d[0] for d in cursor.description]
            row = cursor.fetchone()

        if row is None:
            raise ValueError(f"No record found in '{table}' for {pk_col}={pk_value}")

        record = {}
        for col, val in zip(columns, row):
            if isinstance(val, str):
                try:
                    val = json.loads(val)  # restore JSONB columns
                except (json.JSONDecodeError, ValueError):
                    pass
            record[col] = val
        return record

    def _get_project_id(self, notegroup_id: int) -> int | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT projectID FROM notegroups WHERE notegroupID = ?",
                (notegroup_id,)
            )
            row = cursor.fetchone()
        return row[0] if row else None

    # ── cleanup helpers ──────────────────────────────────────────────────

    @staticmethod
    def _remove_empty(record: dict) -> dict:
        cleaned = {}
        for k, v in record.items():
            if v is None:
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            if isinstance(v, (list, dict)) and len(v) == 0:
                continue
            cleaned[k] = v
        return cleaned

    def _merge_age(self, record: dict) -> None:
        """Replace projectID_age with a single 'age' value using the record's notegroupID."""
        projectID_age = record.pop("projectID_age", None)
        if not projectID_age:
            return
        notegroup_id = record.get("notegroupID")
        if notegroup_id is None:
            return
        project_id = self._get_project_id(notegroup_id)
        record["age"] = projectID_age.get(str(project_id))

    # ── main method ──────────────────────────────────────────────────────

    def DB2json(self) -> str:
        record = self._fetch_record(self.table_name, self.primary_key)

        if self.table_name == "notegroups":
            record = {k: v for k, v in record.items() if k in ("date", "data_source_category")}

        elif self.table_name == "participants":
            record = self._remove_empty(record)
            self._merge_age(record)
            for k in ("participantID", "notegroupID", "country_staying_in"):
                record.pop(k, None)

        elif self.table_name == "questions":
            record = self._remove_empty(record)

            followed_id = record.get("followed_questionID")
            if followed_id is not None:
                followed = self._fetch_record("questions", followed_id)
                record["followed_question_content"] = followed.get("question_content")

            for k in ("questionID", "followed_questionID", "notegroupID"):
                record.pop(k, None)

        elif self.table_name == "answers":
            record = self._remove_empty(record)

            participant = self._remove_empty(
                self._fetch_record("participants", record["participantID"])
            )
            for k in ("notegroupID", "country_staying_in"):
                participant.pop(k, None)
            record.update(participant)

            self._merge_age(record)

            question = self._fetch_record("questions", record["questionID"])
            record["question_content"] = question.get("question_content")

            for k in ("answerID", "notegroupID", "projectID"):
                record.pop(k, None)

        record = self._remove_empty(record)
        return json.dumps(record, ensure_ascii=False)


# --- Usage ---
DB_PATH = "../DB/oedb_baseline_v2.db"

for table, pk in [
    ("notegroups", 7),
    ("participants", 66),
    ("questions", 40),
    ("answers", 1011),
]:
    evaluator = DB2jsonTest(db_path=DB_PATH, table_name=table, primary_key=pk)
    result = evaluator.DB2json()
    print(f"[{table} pk={pk}]")
    print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))
    print()