"""
Test whether the UVA proxy supports OpenAI prompt caching.

Strategy:
  - Send the same long prompt twice (cache requires 1024+ tokens)
  - On the second call, check if prompt_tokens_details.cached_tokens > 0
  - If yes: caching is active and being reported
  - If no / attribute missing: proxy does not support or report caching

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

# ── Build a prompt long enough to be cache-eligible (OpenAI threshold: 1024 tokens)
# ~4 chars per token → need ~4096 chars minimum. We use 5000 to be safe.
LONG_PREFIX = (
    "You are an expert in Dutch civic integration policy. "
    "The following is background context about the Dutch inburgering system. "
    + ("The Wet inburgering 2021 requires municipalities to actively support newcomers "
       "in their integration process, including language acquisition (NT2), "
       "participation modules, and the MAP (Module Arbeidsmarkt en Participatie). ") * 40
    # repeat ~40x to exceed 1024 tokens
)

USER_QUESTION = "Summarise the above in one sentence."

MESSAGES = [
    {"role": "system", "content": LONG_PREFIX},
    {"role": "user",   "content": USER_QUESTION},
]

def call_and_report(label: str) -> int:
    """Make one API call and return cached_tokens (0 if not supported)."""
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=MESSAGES,
    )
    usage = response.usage
    details = getattr(usage, "prompt_tokens_details", None)
    cached  = getattr(details, "cached_tokens", 0) or 0

    logger.info(
        "[%s] input: %d | cached: %d | output: %d | total: %d",
        label,
        usage.prompt_tokens,
        cached,
        usage.completion_tokens,
        usage.total_tokens,
    )
    return cached

# ── First call — nothing should be cached yet ─────────────────────────────────
logger.info("Sending first call (populating cache)...")
call_and_report("call_1")

# Small delay — OpenAI recommends a few seconds before the cache is warm
time.sleep(5)

# ── Second call — identical prompt, cache should kick in ─────────────────────
logger.info("Sending second call (expecting cache hit)...")
cached_tokens = call_and_report("call_2")

# ── Verdict ───────────────────────────────────────────────────────────────────
print()
if cached_tokens > 0:
    print(f"✓ Cache IS supported — {cached_tokens} cached tokens on second call.")
else:
    print("✗ Cache NOT supported (or not reported) — cached_tokens was 0 on second call.")
    print("  Possible reasons:")
    print("  - UVA proxy strips prompt_tokens_details from the response")
    print("  - Proxy does not forward to an OpenAI endpoint that supports caching")
    print("  - Prompt was below the 1024-token cache threshold (unlikely here)")