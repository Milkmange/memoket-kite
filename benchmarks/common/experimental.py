"""Ablation switches for the benchmark bindings.

Nothing here belongs to the memory system. Each switch lets a measurement turn
one mechanism off and compare the arms; unset — which is how every published
number was produced — each takes the binding's own default, so the pipeline is
exactly the one the results describe.

Both bindings resolve their arms through this one implementation, so an arm
name selects the same set of mechanisms whichever binding reads it.

The resolved values are recorded in every run manifest, so a published score
always says which arm produced it.
"""

from __future__ import annotations

import os

#: Every switch is read from the environment under this prefix.
PREFIX = "KITE_"


def arm() -> str:
    """Which arm the process is running.

    Read on every call, never cached at import. A module-level constant would
    freeze whatever the environment held at the moment the profile happened to
    be imported, so a test — or a harness that sets the arm before dispatching
    — could ask for `baseline` and silently get `default`.
    """
    return os.environ.get(f"{PREFIX}ARM", "default")


def flag(name: str, default: bool) -> bool:
    """Whether one mechanism is on, honouring a per-mechanism override first.

    `KITE_ARM=baseline` turns every flag off at once and restores the
    pre-mechanism pipeline; `candidate` turns every flag on. A single
    `KITE_<NAME>=0|1` still wins over the arm. Any other value of either
    is ignored rather than guessed at — a typo must not quietly select an arm.
    """
    override = os.environ.get(f"{PREFIX}{name}", "")
    if override in ("0", "1"):
        return override == "1"
    return {"baseline": False, "candidate": True}.get(arm(), default)


def enabled(name: str, default: bool = False) -> bool:
    """A switch that stands outside the arms.

    Some knobs trade cost for accuracy rather than name a mechanism under test
    — the support check is one — so folding them into `candidate` would change
    what that arm means. They answer only to their own variable.
    """
    override = os.environ.get(f"{PREFIX}{name}", "")
    return override == "1" if override in ("0", "1") else default


def size(name: str, default: int) -> int:
    """A numeric budget, overridable but never zero by accident.

    An empty or unset variable, and an explicit `0`, all mean "use the
    binding's own value" — `0` reads as "no cap" everywhere else, and a stray
    empty variable in a shell should not silently uncap a run.
    """
    return int(os.environ.get(f"{PREFIX}{name}", "0") or 0) or default


def single_call() -> bool:
    """Whether to collapse the answer stage to one LLM call.

    Not a flag: it is a compound arm that switches several mechanisms off
    together, so each binding applies it to its own set at the end of its
    definitions.
    """
    return os.environ.get(f"{PREFIX}SINGLE_CALL") == "1"
