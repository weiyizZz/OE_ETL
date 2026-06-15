from openai import OpenAI
from openai import InternalServerError
from utils.token_logger import TokenLogger
from oral_notes.prompt_combiner import PromptCombiner
from config.config import OPENAI_API_KEY
import json
import time
import sqlite3
from utils.logger import get_logger
import datetime
from pathlib import Path

logger = get_logger(__name__)

class DB1recordEvaluator:

    PK_COLUMNS = {
        "participants": "participantID",
        "questions": "questionID",
        "answers": "answerID",
        "notegroups": "notegroupID",
    }

    TASK_NAMES = {
        "notegroups": "1recordT",
    }

    EVALUATOR_SCHEMA = {
        "type": "json_schema",
        "json_schema": {
            "name": "evaluation_result",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "correct": {"type": "integer", "enum": [0, 1]},
                    "wrong_fields": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["correct", "wrong_fields"],
                "additionalProperties": False
            }
        }
    }

    def __init__(
        self,
        db_path: str,
        prompt_path_evaluator: str,
        schema_path: str,
        text_doc: str,
        file_path_doc: str,
        table_name: str,
        primary_key: int,
        pipeline_type: str,
        evaluator_version: str,
        llm_model: str = "gpt-5.1",
    ):
        self.db_path = db_path
        self.prompt_path_evaluator = prompt_path_evaluator
        self.text_doc = text_doc
        self.file_path_doc = file_path_doc
        self.table_name = table_name
        self.task = self.TASK_NAMES.get(table_name, table_name)
        self.primary_key = primary_key
        self.pipeline_type = pipeline_type
        self.evaluator_version = evaluator_version
        self.llm_model = llm_model
        self.combiner = PromptCombiner(schema_path=schema_path)
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://llmproxy.uva.nl/v1",
            timeout=500.0
        )

    # ── fetch helpers ────────────────────────────────────────────────────────

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

    # ── cleanup helpers ──────────────────────────────────────────────────────

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

    # ── main methods ──────────────────────────────────────────────────────────

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

            for k in ("questionID", "notegroupID"):
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
        json_str = json.dumps(record, ensure_ascii=False)
        logger.debug(
            "DB2json result for '%s' pk=%s:\n%s",
            self.table_name, self.primary_key,
            json.dumps(record, indent=2, ensure_ascii=False)
        )
        return json_str

    def append_evaluation_result(
            self,
            correct: int,
            wrong_fields: list[str],
            eval_log_path: str | Path = "logs/evaluation_results.jsonl",
    ) -> None:
        """Append one evaluation result record to the JSONL log file."""
        eval_log_path = Path(eval_log_path)
        eval_log_path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "pipeline_type": self.pipeline_type,
            "evaluator_version": self.evaluator_version,
            "llm_model": self.llm_model,
            "table_name": self.table_name,
            "primary_key": self.primary_key,
            "correct": correct,
            "wrong_fields": wrong_fields,
        }

        with eval_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(
            "Evaluation [%s pk=%s] correct=%d wrong_fields=%s",
            self.table_name, self.primary_key, correct, wrong_fields
        )

    def evalute_1json(self, max_retries: int = 3, retry_delay: int = 10) -> str:
        json_record = self.DB2json()

        system_prompt = self.combiner.load_prompts_system(self.prompt_path_evaluator)
        user_prompt = self.combiner.build_prompt_user_evaluator(
            prompt_path=self.prompt_path_evaluator,
            task=self.task,
            file_path_doc=self.file_path_doc,
            text_doc=self.text_doc,
            json_record=json_record
        )

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    temperature=0,
                    seed=42,
                    response_format=self.EVALUATOR_SCHEMA,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )

                # ── Token tracking ───────────────────────────────────────────
                usage = response.usage
                cached_tokens = (
                        getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
                )
                TokenLogger.append_evaluator(
                    llm_model=self.llm_model,
                    table_name=self.table_name,
                    primary_key=self.primary_key,
                    evaluator_version=self.evaluator_version,
                    attempt=attempt + 1,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    cached_tokens=cached_tokens,
                    pipeline_type=self.pipeline_type
                )
                # ────────────────────────────────────────────────────────────

                result = response.choices[0].message.content
                parsed = json.loads(result)
                self.append_evaluation_result(
                    correct=parsed["correct"],
                    wrong_fields=parsed["wrong_fields"],
                )
                return

            except InternalServerError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Server error on attempt %d/%d, retrying in %ds...",
                        attempt + 1, max_retries, retry_delay
                    )
                    time.sleep(retry_delay)
                else:
                    raise


