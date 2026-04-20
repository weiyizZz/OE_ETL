import json
import sqlite3
from typing import Literal


class JSON2DBLoader:

    TaskName = Literal["participants", "questions", "answers"]

    def __init__(self, db_path: str, project_id: int):
        self.db_path = db_path
        self.project_id = project_id

    @property
    def FIXED_VALUES(self) -> dict[str, dict]:
        return {
            "participants": {"country_staying_in": "Netherlands"},
            "questions": {},
            "answers": {"projectID": self.project_id},
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

    def load(self, json_str: str, task: TaskName) -> None:
        """
        Parse a JSON string and insert records into the target table.

        Args:
            json_str:  Raw JSON string containing the task's data.
            task:      One of 'participants', 'questions', 'answers'.
        """
        data = json.loads(json_str)
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

participants_json_str = """
{
  "participants": [
    {"participantID": 0, "initials": "K", "gender": "Female", "learning_route": "Z route", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 43}},
    {"participantID": 1, "initials": "E", "gender": "Female", "learning_route": "B1", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Gemert-Bakel", "other_information": null, "projectID_age": {"1": 30}},
    {"participantID": 2, "initials": "A.B", "gender": "Male", "learning_route": "Z route", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Gemert-Bakel", "other_information": null, "projectID_age": {"1": 51}},
    {"participantID": 3, "initials": "N", "gender": "Male", "learning_route": "Z route", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 53}},
    {"participantID": 4, "initials": "H", "gender": "Male", "learning_route": "Z route", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 30}},
    {"participantID": 5, "initials": "W", "gender": "Male", "learning_route": "Z route", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 53}},
    {"participantID": 6, "initials": "F.A", "gender": "Male", "learning_route": "B1", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 32}},
    {"participantID": 7, "initials": "A.A", "gender": "Male", "learning_route": "B1", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 35}},
    {"participantID": 8, "initials": "Y.A", "gender": "Female", "learning_route": "B1", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 40}},
    {"participantID": 9, "initials": "L.H", "gender": "Female", "learning_route": "B1", "participant_group": null, "status": null, "place_of_origin": "Syria", "language_group": null, "first_arrival_date": null, "municipality": "Gemert-Bakel", "other_information": null, "projectID_age": {"1": 50}},
    {"participantID": 10, "initials": "A.N", "gender": "Male", "learning_route": "B1", "participant_group": null, "status": null, "place_of_origin": "Yemen", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 24}},
    {"participantID": 11, "initials": "Z.K", "gender": "Male", "learning_route": "B1", "participant_group": null, "status": null, "place_of_origin": "Yemen", "language_group": null, "first_arrival_date": null, "municipality": "Helmond", "other_information": null, "projectID_age": {"1": 25}}
  ]
}
"""

questions_json_str = """
{
  "questions": [
    {"questionID": 0, "question_content": "How is your inburgering going so far?", "main_indicator": "education", "followed_questionID": null, "following_trigger": null},
    {"questionID": 1, "question_content": "Where do you feel pressure in your life, with the inburgering? What feels difficult to handle?", "main_indicator": "education", "followed_questionID": null, "following_trigger": null},
    {"questionID": 2, "question_content": "Do you work? If yes: is your work paid, or volunteer work?", "main_indicator": "work", "followed_questionID": null, "following_trigger": null},
    {"questionID": 3, "question_content": "How do you feel about your work/volunteer work/not having work?", "main_indicator": "work", "followed_questionID": null, "following_trigger": null},
    {"questionID": 4, "question_content": "At the point you are currently in (within the inburgering), do you feel like you want to be working?", "main_indicator": "work", "followed_questionID": null, "following_trigger": null},
    {"questionID": 5, "question_content": "If you are working/doing volunteer work: Do you feel like your work/volunteer work fits with your skills, interests and needs?", "main_indicator": "work", "followed_questionID": null, "following_trigger": null},
    {"questionID": 6, "question_content": "For everyone in the group: What is missing for you when it comes to work/volunteer work?", "main_indicator": "work", "followed_questionID": null, "following_trigger": null},
    {"questionID": 7, "question_content": "For everyone in the group: What blocks you from getting there?", "main_indicator": "work", "followed_questionID": null, "following_trigger": null},
    {"questionID": 8, "question_content": "What's one thing the municipality can do to make it easier for you to get there?", "main_indicator": "work", "followed_questionID": null, "following_trigger": null},
    {"questionID": 9, "question_content": "Warm up: How often do you feel people are around you, vs how often do you feel people are 'with' you?", "main_indicator": "bridges", "followed_questionID": null, "following_trigger": null},
    {"questionID": 10, "question_content": "What makes it difficult to meet new people?", "main_indicator": "bridges", "followed_questionID": null, "following_trigger": null},
    {"questionID": 11, "question_content": "Do you actively try to meet new people?", "main_indicator": "bridges", "followed_questionID": null, "following_trigger": null},
    {"questionID": 12, "question_content": "If yes: Where do you try to meet new people?", "main_indicator": "bridges", "followed_questionID": "11", "following_trigger": "yes"},
    {"questionID": 13, "question_content": "If no: what stops you from trying?", "main_indicator": "bridges", "followed_questionID": "11", "following_trigger": "no"},
    {"questionID": 14, "question_content": "When you look at your social connections now, who is missing?", "main_indicator": "bridges", "followed_questionID": null, "following_trigger": null},
    {"questionID": 15, "question_content": "What's one thing that the municipality can do to make it easier for you to meet new people?", "main_indicator": "bridges", "followed_questionID": null, "following_trigger": null},
    {"questionID": 16, "question_content": "From the survey, we have seen that many people want to improve their Dutch by practicing it with other people. In what ways would you like that to be set-up?", "main_indicator": "language", "followed_questionID": null, "following_trigger": null},
    {"questionID": 17, "question_content": "Is there anything that we didn't discuss in this session, that you feel is important to add?", "main_indicator": null, "followed_questionID": null, "following_trigger": null},
    {"questionID": 18, "question_content": "Anything that is big and affects your life and needs attention from the municipality?", "main_indicator": null, "followed_questionID": null, "following_trigger": null}
  ]
}
"""

answers_json_str = """
{
  "answers": [
    {"answerID": 0, "questionID": 0, "participantID": 9, "answer_content_oriLAN": "Not good in general. The school is slow and its educational system is not clear, so things are not going well.", "date": null, "data_source_category": "expertpool", "data_source": "https://docs.google.com/document/d/1IMC2OpswPRnubdLWqNJStHWEjb9JTGhL/edit"},
    {"answerID": 1, "questionID": 0, "participantID": 8, "answer_content_oriLAN": "It's not as I hoped. I expected the language study period to be more enjoyable and educational, but unfortunately the reality is different.", "date": null, "data_source_category": "expertpool", "data_source": "https://docs.google.com/document/d/1IMC2OpswPRnubdLWqNJStHWEjb9JTGhL/edit"},
    {"answerID": 2, "questionID": 0, "participantID": 7, "answer_content_oriLAN": "For me, things are not going well. In one class, we have several levels from A1 to A2 to B1. How is that possible?", "date": null, "data_source_category": "expertpool", "data_source": "https://docs.google.com/document/d/1IMC2OpswPRnubdLWqNJStHWEjb9JTGhL/edit"}
  ]
}
"""

# --- Usage ---
loader = JSON2DBLoader(db_path="../DB/oedb_baseline.db", project_id=1)

loader.load(participants_json_str, "participants")
loader.load(questions_json_str, "questions")
loader.load(answers_json_str, "answers")