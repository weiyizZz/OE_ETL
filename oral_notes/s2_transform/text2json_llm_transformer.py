from openai import OpenAI
from openai import InternalServerError
from utils.html_viewer import show
from utils.logger import get_logger
from oral_notes.s2_transform.prompt_combiner import PromptCombiner
from config.config import OPENAI_API_KEY
import json
import time
import datetime
from pathlib import Path

logger = get_logger(__name__)

class Text2JsonTransformer:

    def __init__(
        self,
        prompt_path: str,
        schema_path: str,
        combined_text: str,
        starting_ids: dict,
        file_path_doc: str,
        urls: list[str],
        llm_model: str = "gpt-5.1",
        token_log_path: str = "logs/token_usage.jsonl",
        pipeline_type : str = "baseline"
    ):
        self.prompt_path = prompt_path
        self.combined_text = combined_text
        self.starting_ids = starting_ids
        self.file_path_doc = file_path_doc
        self.urls = urls
        self.llm_model = llm_model
        self.token_log_path = Path(token_log_path)
        self.token_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.pipeline_type = pipeline_type

        self.combiner = PromptCombiner(schema_path=schema_path)

        self.system_prompt = self.combiner.load_prompts_system(prompt_path)
        show(self.system_prompt, title="Prompt for text2json - system")

        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://llmproxy.uva.nl/v1"
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    # Pricing per token (USD), keyed by model name.
    # input_per_1m / output_per_1m match OpenAI's published rates.
    # Add new models here as needed.
    _PRICING: dict[str, dict[str, float]] = {
        "gpt-4.1":  {"input_per_1m": 2.00,  "output_per_1m": 8.00},
        "gpt-4.1-mini": {"input_per_1m": 0.40, "output_per_1m": 1.60},
        "gpt-5.1":  {"input_per_1m": 1.25,  "output_per_1m": 10.00},
    }

    def _calc_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        """Return USD cost for this call, or None if model is not in pricing table."""
        pricing = self._PRICING.get(self.llm_model)
        if pricing is None:
            return None
        return (
                input_tokens * pricing["input_per_1m"] / 1_000_000
                + output_tokens * pricing["output_per_1m"] / 1_000_000
        )

    def _append_token_log(
            self,
            task: str,
            attempt: int,
            input_tokens: int,
            output_tokens: int,
            total_tokens: int
    ) -> None:
        """Append one token-usage record to the JSONL log file."""
        record = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "pipeline_type": self.pipeline_type,
            "llm_model": self.llm_model,
            "urls": self.urls,
            "task": task,
            "attempt": attempt,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": self._calc_cost(input_tokens, output_tokens),
        }
        with self.token_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(
            "Token usage [%s] attempt %d — in: %d, out: %d, total: %d",
            task, attempt, input_tokens, output_tokens, total_tokens
        )

    # ── Core transform ────────────────────────────────────────────────────────

    def transform_1task(
            self,
            task: str,
            output_reduced_participants_pasttask: str = None,
            output_reduced_questions_pasttask: str = None,
            max_retries: int = 3,
            retry_delay: int = 10
    ) -> str:

        user_prompt = self.combiner.build_prompt_user_text2json(
            prompt_path=self.prompt_path,
            task=task,
            text_doc=self.combined_text,
            starting_ids=self.starting_ids,
            file_path_doc=self.file_path_doc,
            output_reduced_participants_pasttask=output_reduced_participants_pasttask,
            output_reduced_questions_pasttask=output_reduced_questions_pasttask
        )
        show(user_prompt, title=f"Prompt for text2json task ({task}) - user")

        json_schema = self.combiner.to_json_schema(task)

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    temperature=0,
                    seed=42,
                    response_format=json_schema,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )

                # ── Token tracking ────────────────────────────────────────────
                usage = response.usage
                self._append_token_log(
                    task=task,
                    attempt=attempt + 1,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                )
                # ─────────────────────────────────────────────────────────────

                result = response.choices[0].message.content
                return result

            except InternalServerError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Server error on attempt %d/%d, retrying in %ds...",
                        attempt + 1, max_retries, retry_delay
                    )
                    time.sleep(retry_delay)
                else:
                    raise

    def transform_3tasks(self) -> dict:

        # ── participants ───────────────────────────────────────────────────────
        result_participants_raw = self.transform_1task(task="participants")
        result_participants = self.postprocess_participants(result_participants_raw, self.starting_ids)
        logger.info("=== Result: participants (from %s) ===\n%s", self.urls, result_participants)
        reduced_result_participants = self.reduce_participants(result_participants)

        # ── questions ──────────────────────────────────────────────────────────
        result_questions = self.transform_1task(task="questions")
        reduced_result_questions = self.reduce_questions(result_questions)

        # ── answers ────────────────────────────────────────────────────────────
        result_answers = self.transform_1task(
            task="answers",
            output_reduced_participants_pasttask=reduced_result_participants,
            output_reduced_questions_pasttask=reduced_result_questions
        )
        logger.info("=== Result: answers (from %s) ===\n%s", self.urls, result_answers)

        # ── postprocess: drop questions with no answers ────────────────────────
        result_questions = self.remove_unanswered_questions(result_questions, result_answers)
        logger.info("=== Result: questions (after removing unanswered, from %s) ===\n%s", self.urls, result_questions)


        return {
            "participants": result_participants,
            "questions": result_questions,
            "answers": result_answers
        }

    @staticmethod
    def postprocess_participants(result_participants: str, starting_ids: dict) -> str:
        data = json.loads(result_participants)
        if isinstance(data, dict):
            data = next(iter(data.values()))
        project_id = starting_ids["projectID"]
        for record in data:
            age = record.pop("age", None)
            record["projectID_age"] = {project_id: age}
        return json.dumps({"participants": data}, ensure_ascii=False)

    @staticmethod
    def remove_unanswered_questions(output_q: str, output_a: str) -> str:
        questions = json.loads(output_q)
        answers = json.loads(output_a)
        questions = next(iter(questions.values()))
        answers = next(iter(answers.values()))

        answered_ids = {record["questionID"] for record in answers if "questionID" in record}
        filtered = [q for q in questions if q.get("questionID") in answered_ids]

        return json.dumps({"questions": filtered}, ensure_ascii=False)

    @staticmethod
    def reduce_participants(output_p: str) -> str:
        data = json.loads(output_p)

        # unwrap if nested under a key e.g. {"participants": [...]}
        if isinstance(data, dict):
            data = next(iter(data.values()))
        reduced = [
            {k: v for k, v in record.items() if v not in ("", None, [], {})}
            for record in data
        ]
        return json.dumps(reduced, ensure_ascii=False)

    @staticmethod
    def reduce_questions(output_q: str) -> str:
        data = json.loads(output_q)

        if isinstance(data, dict):
            data = next(iter(data.values()))
        reduced = [
            {"questionID": record["questionID"], "question_content": record["question_content"]}
            for record in data
        ]
        return json.dumps(reduced, ensure_ascii=False)