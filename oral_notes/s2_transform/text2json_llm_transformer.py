from openai import OpenAI
from openai import InternalServerError
from utils.html_viewer import show
from utils.logger import get_logger
from utils.token_logger import TokenLogger
from oral_notes.s2_transform.prompt_combiner import PromptCombiner
from config.config import OPENAI_API_KEY
import json
import time
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
    ):
        self.prompt_path = prompt_path
        self.combined_text = combined_text
        self.starting_ids = starting_ids
        self.file_path_doc = file_path_doc
        self.urls = urls
        self.llm_model = llm_model

        self.combiner = PromptCombiner(schema_path=schema_path)

        self.system_prompt = self.combiner.load_prompts_system(prompt_path)
        show(self.system_prompt, title="Prompt for text2json - system")

        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://llmproxy.uva.nl/v1"
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
                cached_tokens = (
                    getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
                )
                TokenLogger.append_transformer_baseline(
                    llm_model=self.llm_model,
                    urls=self.urls,
                    task=task,
                    attempt=attempt + 1,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    cached_tokens=cached_tokens,
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