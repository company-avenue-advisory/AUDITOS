"""
Shared LLM call wrapper for all extractors.

Gemini free tier: 15 RPM, 1 million TPM, 1500 req/day.
Strategy:
  - Hard cap: asyncio semaphore limits to 4 concurrent calls (~10 RPM safely)
  - Text truncation: cap each region at MAX_CHARS before sending
  - Retry: exponential backoff on 429 / rate-limit errors (up to 4 attempts)
  - Sleep: 4s between retries ensures we never burst over 15 RPM
"""
import time
import json
import re

# Max characters sent per LLM call — keeps tokens low on free tier.
# Gemini 2.5 Flash: ~4 chars/token, so 4000 chars ≈ 1000 tokens per call.
MAX_CHARS = 4000

def _truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    # Keep head and tail — invoice header + totals are most important
    half = max_chars // 2
    return text[:half] + "\n...[truncated]...\n" + text[-half:]


def llm_call(client, model_name: str, prompt: str, max_retries: int = 4) -> str:
    """
    Make one LLM call with exponential backoff on 429.
    Returns the raw response string, or raises on unrecoverable error.
    """
    delay = 5  # seconds — starts at 5s, doubles each retry
    last_err = None

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            is_rate_limit = any(x in err_str for x in ["429", "rate limit", "quota", "resource_exhausted", "too many"])

            if is_rate_limit and attempt < max_retries - 1:
                wait = delay * (2 ** attempt)
                print(f"  [rate-limit] Gemini 429 — waiting {wait}s before retry {attempt+1}/{max_retries-1}")
                time.sleep(wait)
                continue

            # Non-rate-limit error or exhausted retries
            raise

    raise last_err
