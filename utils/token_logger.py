import json
import datetime
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


class TokenLogger:

    # Pricing per token (USD), keyed by model name.
    # cached_input_per_1m is None if caching is not supported/known for that model.
    # Add new models here as needed.
    _PRICING: dict[str, dict[str, float | None]] = {
        "gpt-4.1":      {"input_per_1m": 2.00,  "cached_input_per_1m": 0.50,  "output_per_1m": 8.00},
        "gpt-5.1":      {"input_per_1m": 1.25,  "cached_input_per_1m": 0.125, "output_per_1m": 10.00},
    }

    @classmethod
    def calc_cost(
        cls,
        llm_model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0
    ) -> float | None:
        """
        Return USD cost for one API call, or None if model is not in the pricing table.

        cached_tokens is a subset of input_tokens (as reported by prompt_tokens_details.cached_tokens).
        uncached_tokens = input_tokens - cached_tokens, billed at full input rate.
        cached_tokens billed at the discounted cached_input rate.
        """
        pricing = cls._PRICING.get(llm_model)
        if pricing is None:
            return None

        uncached_tokens = input_tokens - cached_tokens
        cached_rate = pricing["cached_input_per_1m"] or pricing["input_per_1m"]

        return (
            uncached_tokens * pricing["input_per_1m"] / 1_000_000
            + cached_tokens * cached_rate             / 1_000_000
            + output_tokens * pricing["output_per_1m"] / 1_000_000
        )

    @classmethod
    def append_transformer_baseline(
        cls,
        llm_model: str,
        notegroup_id: int,
        task: str,
        attempt: int,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        token_log_path: str | Path = "logs/token_usage_transformer_baseline.jsonl",
        pipeline_type: str = "baseline",
    ) -> None:
        """Append one token-usage record to the JSONL log file."""
        token_log_path = Path(token_log_path)
        token_log_path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "timestamp":      datetime.datetime.now(datetime.UTC).isoformat(),
            "pipeline_type":  pipeline_type,
            "llm_model":      llm_model,
            "notegroup_id":   notegroup_id,
            "task":           task,
            "attempt":        attempt,
            "input_tokens":   input_tokens,
            "cached_tokens":  cached_tokens,
            "output_tokens":  output_tokens,
            "cost_usd":       cls.calc_cost(llm_model, input_tokens, output_tokens, cached_tokens),
        }

        with token_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(
            "Token usage [%s] attempt %d — in: %d (cached: %d), out: %d, cost: $%.6f",
            task, attempt, input_tokens, cached_tokens, output_tokens,
            record["cost_usd"] or 0.0
        )