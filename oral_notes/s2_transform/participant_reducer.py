import yaml
import time
from openai import OpenAI
from openai import InternalServerError
from utils.html_viewer import show
from utils.logger import get_logger
from utils.token_logger import TokenLogger
from config.config import OPENAI_API_KEY

logger = get_logger(__name__)


class ParticipantReducer:

    def __init__(
        self,
        prompt_path_ParReducer: str,
        all_texts: dict,
        notegroup_id: int,
        llm_model: str = "gpt-5.1",
    ):
        self.prompt_path_ParReducer = prompt_path_ParReducer
        self.all_texts = all_texts
        self.notegroup_id = notegroup_id
        self.llm_model = llm_model

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
                TokenLogger.append_transformer_baseline(
                    llm_model=self.llm_model,
                    notegroup_id=self.notegroup_id,
                    task="ParticipantReducer",
                    attempt=attempt + 1,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    cached_tokens=cached_tokens,
                )
                # ──────────────────────────────────────────────────────────────

                raw = response.choices[0].message.content
                parts = raw.split("###RESULT###")
                if len(parts) < 2:
                    logger.warning(
                        "###RESULT### marker not found in ParticipantReducer response, falling back to original QA text.")
                    return self.all_texts.get("QA", "")
                return parts[-1].strip()

            except InternalServerError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Server error on attempt %d/%d, retrying in %ds...",
                        attempt + 1, max_retries, retry_delay
                    )
                    time.sleep(retry_delay)
                else:
                    raise

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
        logger.info(
            "=== Result: reduced participants (from %s) ===\n%s",
            self.notegroup_id, reduced_par
        )

        return "\n---\n".join([reduced_par, self.all_texts.get("QA", "")])