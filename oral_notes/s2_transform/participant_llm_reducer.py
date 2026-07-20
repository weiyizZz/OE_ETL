import time

import yaml
from openai import InternalServerError
from openai import OpenAI

from config.config import OPENAI_API_KEY
from utils.logger import get_logger
from utils.token_logger import TokenLogger

logger = get_logger(__name__)


class ParticipantReducer:

    def __init__(
        self,
        prompt_path_ParReducer: str,
        all_texts: dict,
        notegroup_id: int,
        pipeline_type: str,
        llm_model: str = "gpt-5.1",
        prompt_path_refiner_ParReducer: str = None,
    ):
        self.prompt_path_ParReducer = prompt_path_ParReducer
        self.all_texts = all_texts
        self.notegroup_id = notegroup_id
        self.pipeline_type = pipeline_type
        self.llm_model = llm_model
        self.prompt_path_refiner_ParReducer = prompt_path_refiner_ParReducer

        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://llmproxy.uva.nl/v1"
        )

    # ── Prompt loaders ────────────────────────────────────────────────────────

    @staticmethod
    def _load_prompts(prompt_path: str) -> dict:
        with open(prompt_path) as f:
            return yaml.safe_load(f)

    def _build_system_prompt(self, prompts: dict) -> str:
        return prompts["system"]

    def _build_user_prompt(self, prompts: dict) -> str:
        text_qa = self.all_texts.get("QA", "")
        text_par = self.all_texts.get("PARTICIPANT", "")
        return prompts["user"]["base"].format(
            text_qa=text_qa,
            text_par=text_par
        )

    def _build_refiner_user_prompt(self, prompts: dict, result_lastcall: str) -> str:
        text_qa = self.all_texts.get("QA", "")
        text_par = self.all_texts.get("PARTICIPANT", "")
        return prompts["user"]["refine"].format(
            text_qa=text_qa,
            text_par=text_par,
            result_lastcall=result_lastcall
        )

    # ── Shared LLM call helper ───────────────────────────────────────────────

    def _call_llm(
            self,
            system_prompt: str,
            user_prompt: str,
            task_for_logging: str,
            max_retries: int = 3,
            retry_delay: int = 10,
    ) -> str:
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    temperature=0,
                    seed=42,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )

                # ── Token tracking ─────────────────────────────────────────────
                usage = response.usage
                cached_tokens = (
                    getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
                )
                TokenLogger.append_transformer(pipeline_type=self.pipeline_type, llm_model=self.llm_model,
                                               notegroup_id=self.notegroup_id,
                                               task=task_for_logging, attempt=attempt + 1,
                                               input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens,
                                               cached_tokens=cached_tokens)
                # ──────────────────────────────────────────────────────────────

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

    @staticmethod
    def _extract_result_marker(raw: str, fallback: str, fallback_warning: str) -> str:
        parts = raw.split("###RESULT###")
        if len(parts) < 2:
            logger.warning(fallback_warning)
            return fallback
        return parts[-1].strip()

    # ── Refiner ───────────────────────────────────────────────────────────────

    def _refine(self, result_lastcall: str) -> str:
        """
        Single-round refinement pass over the reduced participants' text.
        Returns result_lastcall unchanged if the refiner passes (no
        correction needed) or if the ###RESULT### marker is missing.
        """
        prompts = self._load_prompts(self.prompt_path_refiner_ParReducer)
        system_prompt = prompts["system"]
        user_prompt = self._build_refiner_user_prompt(prompts, result_lastcall)

        raw = self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_for_logging="ParticipantReducer_refiner",
        )

        result = self._extract_result_marker(
            raw,
            fallback=result_lastcall,
            fallback_warning=(
                "###RESULT### marker not found in ParticipantReducer refiner response, "
                "keeping previous result."
            ),
        )

        logger.info(
            "=== Result: ParticipantReducer refiner round 1/1 (from %s) ===\n%s",
            self.notegroup_id, result
        )

        if result.strip().lower() == "pass":
            logger.info(
                "ParticipantReducer refiner passed, returning previous result. (notegroup=%s)",
                self.notegroup_id
            )
            return result_lastcall

        return result

    # ── Core reduction ────────────────────────────────────────────────────────

    def reduce(
        self,
        max_retries: int = 3,
        retry_delay: int = 10
    ) -> str:
        """
        Call the LLM to filter the participants' information transcript,
        retaining only participants present in the session transcript.

        Returns the reduced participants text (as returned by the LLM).
        """
        prompts = self._load_prompts(self.prompt_path_ParReducer)
        system_prompt = self._build_system_prompt(prompts)
        user_prompt = self._build_user_prompt(prompts)

        #show(user_prompt, title="Prompt for ParticipantReducer - user")

        raw = self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_for_logging="ParticipantReducer",
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        result = self._extract_result_marker(
            raw,
            fallback=self.all_texts.get("QA", ""),
            fallback_warning=(
                "###RESULT### marker not found in ParticipantReducer response, "
                "falling back to original QA text."
            ),
        )

        logger.info(
            "=== Result: reduced participants (before refinement, from %s) ===\n%s",
            self.notegroup_id, result
        )

        if isinstance(self.pipeline_type, str) and self.pipeline_type.startswith("refiner"):
            result = self._refine(result)

        return result

    # ── Output builder ────────────────────────────────────────────────────────

    def build_combined_text(self) -> str:
        """
        Run the participant reduction and return the combined text with
        the reduced participants' transcript replacing the original,
        joined with the original QA transcript.

        Output format mirrors the input convention:
            <reduced PARTICIPANT text>
            ---
            <original QA text>
        """
        reduced_par = self.reduce()
        return "\n---\n".join([
            f"## Participants' Information Transcript\n{reduced_par}",
            f"## Session Transcript\n{self.all_texts.get('QA', '')}"
        ])