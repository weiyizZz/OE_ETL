from openai import OpenAI
from openai import InternalServerError
from utils.logger import get_logger
from utils.token_logger import TokenLogger
from oral_notes.prompt_combiner_v3 import PromptCombiner
from config.config import OPENAI_API_KEY
import json
import time
from utils.html_viewer import show

logger = get_logger(__name__)

REFINABLE_TASKS = ("participants", "questions", "answers", "1recordT")

class Text2JsonTransformer:

    def __init__(
        self,
        prompt_path_text2json: str,
        prompt_path_1recordT: str,
        schema_path: str,
        combined_text: str,
        starting_ids: dict,
        file_path_doc: str,
        notegroup_id: int,
        pipeline_type: str,
        has_participant: bool = False,
        llm_model: str = "gpt-5.1",
        prompt_path_refiner_pqa: str = None,
        prompt_path_refiner_1recordT: str = None,
    ):
        self.prompt_path_text2json = prompt_path_text2json
        self.prompt_path_1recordT = prompt_path_1recordT
        self.combined_text = combined_text
        self.starting_ids = starting_ids
        self.file_path_doc = file_path_doc
        self.notegroup_id = notegroup_id
        self.pipeline_type = pipeline_type
        self.has_participant = has_participant
        self.llm_model = llm_model
        self.prompt_path_refiner_pqa = prompt_path_refiner_pqa
        self.prompt_path_refiner_1recordT = prompt_path_refiner_1recordT

        self.combiner = PromptCombiner(schema_path=schema_path)

        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://llmproxy.uva.nl/v1",
            timeout=500.0
        )

    # ── Shared LLM call helper ──────────────────────────────────────────────

    def _call_llm(
            self,
            system_prompt: str,
            user_prompt: str,
            json_schema: dict,
            task_for_logging: str,
            max_retries: int = 5,
            retry_delay: int = 10,
    ) -> str:
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    temperature=0,
                    seed=42,
                    response_format=json_schema,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )

                # ── Token tracking ────────────────────────────────────────────
                usage = response.usage
                cached_tokens = (
                    getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
                )
                TokenLogger.append_transformer(llm_model=self.llm_model, notegroup_id=self.notegroup_id,
                                               task=task_for_logging, attempt=attempt + 1,
                                               input_tokens=usage.prompt_tokens,
                                               output_tokens=usage.completion_tokens, cached_tokens=cached_tokens,
                                               pipeline_type=self.pipeline_type)
                # ─────────────────────────────────────────────────────────────

                return response.choices[0].message.content

            except InternalServerError:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Server error on attempt %d/%d (task=%s), retrying in %ds...",
                        attempt + 1, max_retries, task_for_logging, retry_delay
                    )
                    time.sleep(retry_delay)
                else:
                    raise

    # ── Refiner loop ─────────────────────────────────────────────────────────

    def _get_max_refiner_rounds(self, task: str) -> int:
        if self.pipeline_type == "refiner_1st" and task == "answers":
            return 2
        return 1

    def _refine_result(
            self,
            task: str,
            current_result: str,
            json_schema: dict,
            output_reduced_participants_pasttask: str = None,
            output_reduced_questions_pasttask: str = None,
    ) -> str:
        max_rounds = self._get_max_refiner_rounds(task)

        if task == "1recordT":
            system_prompt = self.combiner.load_prompts_system(self.prompt_path_refiner_1recordT)
            def build_user_prompt(last_result: str) -> str:
                return self.combiner.build_prompt_user_refiner_1recordT(
                    prompt_path=self.prompt_path_refiner_1recordT,
                    file_path_doc=self.file_path_doc,
                    text_doc=self.combined_text,
                    json_result_lastcall=last_result,
                )
        else:
            system_prompt = self.combiner.build_prompt_system_refiner_pqa(
                prompt_path=self.prompt_path_refiner_pqa,
                task=task
            )
            def build_user_prompt(last_result: str) -> str:
                return self.combiner.build_prompt_user_refiner_pqa(
                    prompt_path=self.prompt_path_refiner_pqa,
                    task=task,
                    text_doc=self.combined_text,
                    json_result_lastcall=last_result,
                    starting_ids=self.starting_ids,
                    output_reduced_participants_pasttask=output_reduced_participants_pasttask,
                    output_reduced_questions_pasttask=output_reduced_questions_pasttask,
                )

        pass_placeholder = self.combiner.build_pass_placeholder(task)

        for round_num in range(1, max_rounds + 1):
            user_prompt = build_user_prompt(current_result)
            result = self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema=json_schema,
                task_for_logging=task + "_refiner_round" + str(round_num),
                retry_delay=60,
            )
            logger.info(
                "=== Result: %s refiner round %d/%d (from %s) ===\n%s",
                task, round_num, max_rounds, self.notegroup_id, result
            )
            try:
                parsed = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if parsed == pass_placeholder:
                logger.info(
                    "Passed on round %d, returning previous result. (task=%s, notegroup=%s)",
                    round_num, task, self.notegroup_id
                )
                return current_result
            try:
                no_change = parsed == json.loads(current_result)
            except (json.JSONDecodeError, TypeError):
                no_change = False
            current_result = result
            if no_change:
                logger.info(
                    "No change from previous round on round %d, stopping early. (task=%s, notegroup=%s)",
                    round_num, task, self.notegroup_id
                )
                break
        return current_result

    # ── Core transform ────────────────────────────────────────────────────────

    def transform_1task(
            self,
            task: str,
            output_reduced_participants_pasttask: str = None,
            output_reduced_questions_pasttask: str = None,
            max_retries: int = 5,
            retry_delay: int = 10
    ) -> str:
        if task == "1recordT":
            system_prompt = self.combiner.load_prompts_system(self.prompt_path_1recordT)
            user_prompt = self.combiner.build_prompt_user_1recordT(
                prompt_path=self.prompt_path_1recordT,
                file_path_doc=self.file_path_doc,
                text_doc=self.combined_text
            )
            #show(user_prompt, title=f"{self.notegroup_id} | text2json: {task} | {self.pipeline_type} | prompt")

        else:
            system_prompt = self.combiner.load_prompts_system(self.prompt_path_text2json)
            user_prompt = self.combiner.build_prompt_user_text2json(
                prompt_path=self.prompt_path_text2json,
                task=task,
                text_doc=self.combined_text,
                starting_ids=self.starting_ids,
                output_reduced_participants_pasttask=output_reduced_participants_pasttask,
                output_reduced_questions_pasttask=output_reduced_questions_pasttask,
                has_participant=self.has_participant
            )
            #show(user_prompt, title=f"{self.notegroup_id} | text2json: {task} | {self.pipeline_type} | prompt")

        json_schema = self.combiner.to_json_schema(task)

        result = self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            task_for_logging=task,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        logger.info(
            "=== Result: %s (initial without refinement, from %s) ===\n%s",
            task, self.notegroup_id, result
        )

        # ── Refinement loop ──────────────────────────────────────────────────
        if self.pipeline_type.startswith("refiner") and task in REFINABLE_TASKS:
            result = self._refine_result(
                task=task,
                current_result=result,
                output_reduced_participants_pasttask=output_reduced_participants_pasttask,
                output_reduced_questions_pasttask=output_reduced_questions_pasttask,
            )

        return result

    def transform_4tasks(self) -> dict:

        # ── participants ───────────────────────────────────────────────────────
        result_participants_raw = self.transform_1task(task="participants")
        reduced_result_participants = self.reduce_participants(result_participants_raw)

        # ── questions ──────────────────────────────────────────────────────────
        result_questions = self.transform_1task(task="questions")
        reduced_result_questions = self.reduce_questions(result_questions)

        # ── answers ────────────────────────────────────────────────────────────
        result_answers = self.transform_1task(
            task="answers",
            output_reduced_participants_pasttask=reduced_result_participants,
            output_reduced_questions_pasttask=reduced_result_questions,
            retry_delay=60
        )
        #logger.info("=== Result: answers (from %s) ===\n%s", self.notegroup_id, result_answers)

        # ── postprocess: drop participants with no answers ─────────────────────
        result_participants = self.postprocess_participants(result_participants_raw, self.starting_ids)
        result_participants = self.remove_unanswered_participants(result_participants, result_answers)
        logger.info("=== Result: participants (after removing unanswering, from %s) ===\n%s", self.notegroup_id, result_participants)

        # ── postprocess: drop questions with no answers ────────────────────────
        result_questions = self.remove_unanswered_questions(result_questions, result_answers)
        logger.info("=== Result: questions (after removing unanswered, from %s) ===\n%s", self.notegroup_id, result_questions)

        # ── 1recordT ────────────────────────────────────────────────────────────
        result_1recordT = self.transform_1task(task="1recordT")
        #logger.info("=== Result: 1recordT (from %s) ===\n%s", self.notegroup_id, result_1recordT)

        return {
            "participants": result_participants,
            "questions": result_questions,
            "answers": result_answers,
            "1recordT": result_1recordT
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
    def remove_unanswered_participants(result_participants: str, result_answers: str) -> str:
        participants = json.loads(result_participants)
        answers = json.loads(result_answers)
        participants = next(iter(participants.values()))
        answers = next(iter(answers.values()))

        answering_ids = {record["participantID"] for record in answers if "participantID" in record}
        filtered = [p for p in participants if p.get("participantID") in answering_ids]

        return json.dumps({"participants": filtered}, ensure_ascii=False)

    @staticmethod
    def remove_unanswered_questions(output_q: str, output_a: str) -> str:
        # While keeping the followed questions
        questions = json.loads(output_q)
        answers = json.loads(output_a)
        questions = next(iter(questions.values()))
        answers = next(iter(answers.values()))

        answered_ids = {record["questionID"] for record in answers if "questionID" in record}
        followed_ids = {
            q["followed_questionID"] for q in questions
            if q.get("followed_questionID") is not None
               and q.get("questionID") in answered_ids
        }
        keep_ids = answered_ids | followed_ids
        filtered = [q for q in questions if q.get("questionID") in keep_ids]

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