"""
Shared LLM call wrapper for all extractors.

Gemini free tier: 15 RPM, 1 million TPM, 1500 req/day.
Strategy:
  - Circuit breaker: per-provider CLOSED → OPEN → HALF_OPEN state machine.
    Prevents cascading failures when a provider is down — fails fast instead
    of burning retries across every invoice in a batch.
  - Exponential backoff: on 429 / rate-limit errors (up to 4 attempts, 5s base)
  - Text truncation: cap each region at MAX_CHARS before sending
"""
import time
import threading
from enum import Enum

# Max characters sent per LLM call — keeps tokens low on free tier.
# Gemini 2.5 Flash: ~4 chars/token, so 4000 chars ≈ 1000 tokens per call.
MAX_CHARS = 4000

def _truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n...[truncated]...\n" + text[-half:]


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
# Each LLM provider gets its own breaker instance, keyed by provider name.
# States:
#   CLOSED   — normal operation; failures are counted
#   OPEN     — provider is down; calls fail immediately for COOLDOWN_SECS
#   HALF_OPEN — cooldown elapsed; one probe call allowed through to test recovery
#
# Thresholds (tunable via env vars or defaults below):
#   FAILURE_THRESHOLD = 5   consecutive failures → OPEN
#   COOLDOWN_SECS     = 60  seconds in OPEN before moving to HALF_OPEN
# ---------------------------------------------------------------------------

class _CBState(Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    FAILURE_THRESHOLD = 5
    COOLDOWN_SECS     = 60

    def __init__(self, provider: str):
        self.provider        = provider
        self.state           = _CBState.CLOSED
        self.failure_count   = 0
        self.opened_at: float = 0.0
        self._lock           = threading.Lock()

    def _should_open(self) -> bool:
        return self.failure_count >= self.FAILURE_THRESHOLD

    def allow_request(self) -> bool:
        with self._lock:
            if self.state == _CBState.CLOSED:
                return True
            if self.state == _CBState.OPEN:
                elapsed = time.monotonic() - self.opened_at
                if elapsed >= self.COOLDOWN_SECS:
                    self.state = _CBState.HALF_OPEN
                    print(f"  [CircuitBreaker:{self.provider}] HALF_OPEN — probing recovery.")
                    return True
                return False
            # HALF_OPEN — allow exactly one probe through
            return True

    def record_success(self):
        with self._lock:
            if self.state in (_CBState.HALF_OPEN, _CBState.OPEN):
                print(f"  [CircuitBreaker:{self.provider}] CLOSED — provider recovered.")
            self.state         = _CBState.CLOSED
            self.failure_count = 0

    def record_failure(self, err: Exception):
        with self._lock:
            self.failure_count += 1
            if self.state == _CBState.HALF_OPEN:
                # Probe failed — reopen immediately
                self.state     = _CBState.OPEN
                self.opened_at = time.monotonic()
                print(f"  [CircuitBreaker:{self.provider}] OPEN (probe failed) — cooldown {self.COOLDOWN_SECS}s.")
            elif self._should_open():
                self.state     = _CBState.OPEN
                self.opened_at = time.monotonic()
                print(f"  [CircuitBreaker:{self.provider}] OPEN after {self.failure_count} failures — cooldown {self.COOLDOWN_SECS}s. Last error: {err}")

    def status(self) -> dict:
        with self._lock:
            return {
                "provider":      self.provider,
                "state":         self.state.value,
                "failure_count": self.failure_count,
                "cooldown_remaining": max(0, self.COOLDOWN_SECS - (time.monotonic() - self.opened_at))
                                      if self.state == _CBState.OPEN else 0,
            }


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is OPEN."""
    pass


# One breaker per provider — shared across all threads/coroutines.
_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()

def _get_breaker(provider: str) -> CircuitBreaker:
    with _breakers_lock:
        if provider not in _breakers:
            _breakers[provider] = CircuitBreaker(provider)
        return _breakers[provider]


def get_all_breaker_status() -> list[dict]:
    """Returns status of all circuit breakers — used by /api/health/workers."""
    with _breakers_lock:
        return [b.status() for b in _breakers.values()]


# ---------------------------------------------------------------------------
# LLM call with circuit breaker + exponential backoff
# ---------------------------------------------------------------------------

def _infer_provider(model_name: str, provider: str) -> str:
    """Derive a stable provider key from model name when not explicitly passed."""
    if provider != "default":
        return provider
    m = model_name.lower()
    if "gemini" in m or "google" in m:
        return "gemini"
    if "groq" in m or "llama" in m or "mixtral" in m:
        return "groq"
    if "openrouter" in m or "meta-llama" in m or "mistral" in m:
        return "openrouter"
    if "claude" in m or "anthropic" in m:
        return "anthropic"
    if "ollama" in m or "qwen" in m or "phi" in m:
        return "ollama"
    return "default"


def llm_call(client, model_name: str, prompt: str, max_retries: int = 4,
             provider: str = "default") -> str:
    """
    Make one LLM call with:
      1. Circuit breaker — fails fast if provider is known-down
      2. Exponential backoff — on 429 / rate-limit errors only

    Args:
        client:      OpenAI-compatible client instance
        model_name:  Model identifier string
        prompt:      The prompt text
        max_retries: Max retry attempts on rate-limit errors
        provider:    Provider name for circuit breaker keying (groq/gemini/openrouter/ollama)

    Raises:
        CircuitOpenError: if the circuit is OPEN (provider is down)
        Exception:        on unrecoverable API errors
    """
    provider = _infer_provider(model_name, provider)
    breaker = _get_breaker(provider)

    if not breaker.allow_request():
        status = breaker.status()
        raise CircuitOpenError(
            f"Provider '{provider}' circuit is OPEN — "
            f"{status['cooldown_remaining']:.0f}s cooldown remaining. "
            f"Skipping to avoid cascading failures."
        )

    delay = 5  # base backoff seconds
    last_err = None

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            result = response.choices[0].message.content.strip()
            breaker.record_success()
            return result

        except CircuitOpenError:
            raise

        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            is_rate_limit = any(x in err_str for x in [
                "429", "rate limit", "quota", "resource_exhausted", "too many requests"
            ])
            is_transient = any(x in err_str for x in [
                "500", "502", "503", "504", "timeout", "connection", "unavailable"
            ])

            if is_rate_limit and attempt < max_retries - 1:
                wait = delay * (2 ** attempt)
                print(f"  [LLM:{provider}] 429 rate-limit — waiting {wait}s (retry {attempt+1}/{max_retries-1})")
                time.sleep(wait)
                continue

            # Record failure in circuit breaker for transient/server errors
            if is_transient or is_rate_limit:
                breaker.record_failure(e)

            raise

    # Exhausted all retries
    if last_err:
        breaker.record_failure(last_err)
    raise last_err
