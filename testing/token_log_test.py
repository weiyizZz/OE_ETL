"""
End-to-end test for token tracking via a real (cheap) API call.

Sends "hello" as the prompt to the UVA proxy, then verifies that:
  1. The API returns a response
  2. token usage fields are present and non-zero
  3. a JSONL record is written correctly

Run from your project root:

    python test_token_log.py

One record will be appended to logs/test_token_usage.jsonl.
"""

import json
import logging
import datetime
from pathlib import Path

from openai import OpenAI
from pydantic.experimental import pipeline

from config.config import OPENAI_API_KEY

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

LOG_PATH = Path("logs/test_token_usage.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────────────

URLS      = ["https://drive.google.com/file/d/abc123"]
TASK      = "hello_test"
pipeline_TYPE = "baseline"

# ── Real API call ─────────────────────────────────────────────────────────────

client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://llmproxy.uva.nl/v1")

response = client.chat.completions.create(
    model="gpt-4.1",
    temperature=0,
    messages=[{"role": "user", "content": "hello"}]
)

reply  = response.choices[0].message.content
usage  = response.usage

logger.info("Model reply: %s", reply)
logger.info("Token usage — in: %d, out: %d, total: %d",
            usage.prompt_tokens, usage.completion_tokens, usage.total_tokens)

# ── Write log record (same logic as _append_token_log) ───────────────────────

record = {
    "timestamp":     datetime.datetime.now(datetime.UTC).isoformat(),
    "pipeline_type": pipeline_TYPE,
    "urls":          URLS,
    "task":          TASK,
    "attempt":       1,
    "input_tokens":  usage.prompt_tokens,
    "output_tokens": usage.completion_tokens,
    "total_tokens":  usage.total_tokens,
}

with LOG_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

# ── Verify ────────────────────────────────────────────────────────────────────

records = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines()]
assert records[0]["input_tokens"]  > 0,            "input_tokens should be > 0"
assert records[0]["output_tokens"] > 0,            "output_tokens should be > 0"
assert records[0]["task"] == TASK,                 "task field mismatch"

print(f"\n✓ Token log verified — {LOG_PATH}\n")
print(json.dumps(records[0], indent=2))