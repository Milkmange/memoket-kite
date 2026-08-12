"""Channel ledger: observation-only token accounting per question.

Books every contributor to the shipped answer prompt (rows, neighbor lines,
context blocks, retry calls) in two currencies — the compact admission
convention used by the token cap, and the real rendered token count — without
altering a single byte of any prompt or the call topology. When no ledger is
active every hook is a no-op, so instrumented code paths behave identically
with and without telemetry.
"""

from __future__ import annotations

import threading

from memoket_kite.errors import ConfigurationError

_STATE = threading.local()

_TOKEN_ENCODER = None


def text_tokens(text: str) -> int:
    """Token count of rendered text.

    Uses the ``o200k_base`` encoding when ``tiktoken`` is installed (it ships
    with the ``benchmark`` extra) and a character estimate otherwise, so the
    kernel keeps working without the optional dependency."""
    global _TOKEN_ENCODER
    if _TOKEN_ENCODER is None:
        try:
            import tiktoken

            _TOKEN_ENCODER = tiktoken.get_encoding("o200k_base")
        except Exception:
            _TOKEN_ENCODER = False
    if _TOKEN_ENCODER:
        return len(_TOKEN_ENCODER.encode(text))
    return len(text) // 4


# Channels that re-measure part of another channel for diagnosis. They are
# reported but never summed, or the total counts the same text twice.
SUBSET_CHANNELS = frozenset({"bound_rows"})


def tokenizer_name() -> str:
    """Name the counter behind these numbers.

    The exact encoding and the character estimate disagree on the same text,
    so a reported token figure is only interpretable alongside its unit.
    """
    text_tokens("")  # resolve the encoder on first use
    return "o200k_base" if _TOKEN_ENCODER else "chars//4 (tiktoken unavailable)"


def require_exact_tokenizer(reason: str) -> None:
    """Refuse to price rows with the character estimate.

    The fallback is fine for a report. It is not fine for admission: the same
    row costs a different number of tokens under `chars//4`, so a budgeted
    pack admits a different set of rows and the pipeline silently becomes a
    different pipeline.
    """
    text_tokens("")
    if not _TOKEN_ENCODER:
        # A library must not sentence the host process to death, so this is a
        # catchable ConfigurationError rather than SystemExit: SystemExit
        # derives from BaseException and passes straight through the
        # `except Exception` boundaries an embedding application relies on.
        # The benchmark CLIs check this once at startup and map it to a clean
        # exit themselves.
        raise ConfigurationError(
            f"{reason} needs an exact token count, but the o200k_base encoding is "
            f"unavailable, so rows would be priced by `len(text)//4` and a different "
            f"pack would be admitted. Install the `benchmark` extra; if it is already "
            f"installed, tiktoken could not fetch its encoding table — run once with "
            f"network access, or point TIKTOKEN_CACHE_DIR at a warm cache. Setting "
            f"the budget to 0 disables the cap instead."
        )


class ChannelLedger:
    """Per-question spend accumulator; one instance per answer() invocation."""

    def __init__(self) -> None:
        self.channels: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.notes: dict = {}

    def charge(self, channel: str, *, compact: int = 0, real: int = 0, n: int = 1) -> None:
        entry = self.channels.setdefault(channel, {"compact": 0, "real": 0, "n": 0})
        entry["compact"] += int(compact)
        entry["real"] += int(real)
        entry["n"] += int(n)

    def call(self, site: str, prompt: str) -> None:
        self.calls.append({"site": site, "prompt_tokens": text_tokens(prompt)})

    def snapshot(self) -> dict:
        billed = [entry for name, entry in self.channels.items() if name not in SUBSET_CHANNELS]
        return {
            "channels": self.channels,
            "reader_calls": self.calls,
            # The row-admission budget: what the packer priced when deciding
            # what to seat. Blocks added after selection are NOT part of it —
            # for what the reader received, read `real_total`.
            "compact_total": sum(c["compact"] for c in billed),
            "real_total": sum(c["real"] for c in billed),
            "call_total": len(self.calls),
            "prompt_tokens_max": max((c["prompt_tokens"] for c in self.calls), default=0),
            "notes": self.notes,
        }


def begin() -> ChannelLedger:
    _STATE.ledger = ChannelLedger()
    return _STATE.ledger


def current() -> ChannelLedger | None:
    return getattr(_STATE, "ledger", None)


def snapshot() -> dict | None:
    """Current accounting, or None when no ledger is active."""
    led = current()
    return led.snapshot() if led is not None else None


def end() -> None:
    """Close the active ledger."""
    _STATE.ledger = None


def charge(channel: str, *, compact: int = 0, real: int = 0, n: int = 1) -> None:
    led = current()
    if led is not None:
        led.charge(channel, compact=compact, real=real, n=n)


def call(site: str, prompt: str) -> None:
    led = current()
    if led is not None:
        led.call(site, prompt)


def note(key: str, value) -> None:
    led = current()
    if led is not None:
        led.notes[key] = value
