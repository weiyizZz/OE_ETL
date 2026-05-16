"""
Test whether caching works on a shared prefix with different tails.

Strategy:
  - Call 1: long system prompt + user question A
  - Call 2: same long system prompt + different user question B
  - If cached_tokens > 0 on call 2: prefix caching works even with different tails
  - If cached_tokens == 0: caching only works on fully identical prompts

Run from your project root:
    python test_cache_input.py
"""

import time
import logging
from openai import OpenAI
from config.config import OPENAI_API_KEY

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://llmproxy.uva.nl/v1")
MODEL = "gpt-5.1"

# ── Shared prefix — long enough to be cache-eligible (1024+ tokens)
# ~4 chars per token → need ~4096 chars minimum. We use 5000 to be safe.
LONG_PREFIX = (
    "You are an expert in Dutch civic integration policy. "
    "The following is background context about the Dutch inburgering system. "
    + ("The Wet inburgering 2021 requires municipalities to actively support newcomers "
       "in their integration process, including language acquisition (NT2), "
       "participation modules, and the MAP (Module Arbeidsmarkt en Participatie). ") * 40
)

# ── Different tails — simulating different tasks sharing the same prefix
USER_QUESTIONS = {
    "call_1": "Summarise the above in one sentence.",
    "call_2": "List the key policy obligations mentioned above.",  # different tail
}


def call_and_report(label: str) -> int:
    """Make one API call with a label-specific tail and return cached_tokens."""
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": LONG_PREFIX},
            {"role": "user",   "content": USER_QUESTIONS[label]},
        ],
    )
    usage = response.usage
    details = getattr(usage, "prompt_tokens_details", None)
    cached  = getattr(details, "cached_tokens", 0) or 0

    logger.info(
        "[%s] input: %d | cached: %d | output: %d | tail: %r",
        label,
        usage.prompt_tokens,
        cached,
        usage.completion_tokens,
        USER_QUESTIONS[label],
    )
    return cached


# ── First call — warms the cache with LONG_PREFIX ─────────────────────────────
logger.info("Sending first call (populating cache, tail A)...")
call_and_report("call_1")

time.sleep(5)

# ── Second call — same prefix, different tail ─────────────────────────────────
logger.info("Sending second call (different tail B, expecting prefix cache hit)...")
cached_tokens = call_and_report("call_2")

# ── Verdict ───────────────────────────────────────────────────────────────────
print()
if cached_tokens > 0:
    print(f"✓ Prefix caching works with different tails — {cached_tokens} cached tokens.")
    print("  Your 3-task pipeline will benefit from caching on calls 2 and 3.")
else:
    print("✗ No cache hit — caching may require fully identical prompts end-to-end.")
    print("  Cached input pricing will not apply to your pipeline.")