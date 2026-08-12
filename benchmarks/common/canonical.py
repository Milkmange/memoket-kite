"""Score against the dataset, not against the file the system wrote.

A result row is the system's answer plus its telemetry. Everything the judge
needs — the question, the gold, the category — belongs to the frozen corpus.
Reading those from the row and merely comparing them leaves the comparison
optional in practice: a forged gold passes as long as the ids line up, and a
row can be dropped or duplicated without changing a set of keys.

So the row supplies identity and answer; the dataset supplies the rest.
"""

from __future__ import annotations


def reconcile(rows: list[dict], expected: dict, key_of, fields: tuple[str, ...]) -> list[dict]:
    """Bind each row to its dataset entry, refusing anything that does not fit.

    `expected` maps identity -> the frozen dataset item. Rows are admitted one
    at a time rather than compared as a set of keys, because a set cannot see a
    repeated row: an extra copy of an answered question leaves the key set
    exactly equal to the corpus while moving the denominator.

    Coverage is then checked in both directions — an unanswered question and a
    row belonging to no dataset entry are equally disqualifying. Each
    `(name, source_name)` pair in `fields` copies one value from the dataset
    entry onto the row, overwriting whatever the row carried, so the judge
    reads the gold from the corpus and never from what the system wrote.
    """
    seen: dict = {}
    for row in rows:
        identity = key_of(row)
        if identity in seen:
            raise SystemExit(f"{identity} appears twice in the results; the run is not clean")
        seen[identity] = row
    missing = sorted(set(expected) - set(seen), key=str)
    foreign = sorted(set(seen) - set(expected), key=str)
    if missing or foreign:
        raise SystemExit(
            f"the run does not cover the corpus it declared: {len(missing)} unanswered, "
            f"{len(foreign)} not in the dataset "
            f"(e.g. missing {missing[:2]}, foreign {foreign[:2]})"
        )
    for identity, row in seen.items():
        item = expected[identity]
        for name, source_name in fields:
            row[name] = item[source_name]
    return list(seen.values())
