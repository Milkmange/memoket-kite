"""LoCoMo evaluation protocol and deterministic metrics."""

from __future__ import annotations

import collections
import re
import string

CATEGORIES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop"}

JUDGE_PROMPT = """You are grading a memory system's answer against a gold answer.
Output a binary verdict: CORRECT or WRONG.

Grade leniently, on recalled knowledge rather than wording:
- If the gold answer is a list, ANY one correctly recalled item earns CORRECT.
- Paraphrases and same-meaning rewordings are CORRECT; for feelings, the same
  positive/negative sentiment about the same event is enough.
- Extra detail beyond the gold answer never hurts, as long as the core fact is
  there and not contradicted.
- Dates within about two weeks, and durations within about 50%, count as
  matching; a specific date consistent with a vague gold reference also counts.
- Referring to the same entity/person/event as the gold answer is CORRECT even
  if described differently.
Mark WRONG only when the answer shares nothing correct with the gold answer or
talks about something else entirely.

Question: {question}
Gold answer: {answer}
Generated answer: {response}

Return JSON with "reasoning" (one sentence) and "label" (CORRECT or WRONG)."""


def preprocess_answer(category: int, answer: str) -> str:
    """Apply the published category-3 gold-answer normalization."""
    if category == 3 and ";" in answer:
        return answer.split(";", 1)[0].strip()
    return answer


def _tokens(text: str) -> list[str]:
    normalized = str(text).lower()
    normalized = "".join(char for char in normalized if char not in string.punctuation)
    return re.sub(r"\b(a|an|the)\b", " ", normalized).split()


def token_f1(prediction: str, reference: str) -> float:
    prediction_tokens, reference_tokens = _tokens(prediction), _tokens(reference)
    if not prediction_tokens or not reference_tokens:
        return float(prediction_tokens == reference_tokens)
    overlap = sum(
        (collections.Counter(prediction_tokens) & collections.Counter(reference_tokens)).values()
    )
    return 0.0 if overlap == 0 else 2 * overlap / (len(prediction_tokens) + len(reference_tokens))


def bleu1(prediction: str, reference: str) -> float:
    prediction_tokens, reference_tokens = _tokens(prediction), _tokens(reference)
    if not prediction_tokens:
        return 0.0
    overlap = sum(
        (collections.Counter(prediction_tokens) & collections.Counter(reference_tokens)).values()
    )
    precision = overlap / len(prediction_tokens)
    brevity = (
        1.0
        if len(prediction_tokens) >= len(reference_tokens)
        else pow(2.718281828, 1 - len(reference_tokens) / max(1, len(prediction_tokens)))
    )
    return brevity * precision


def summarize(records: list[dict]) -> dict:
    """Compute deterministic aggregate metrics from judged records."""
    categories = collections.defaultdict(lambda: collections.defaultdict(float))
    for record in records:
        category = int(record["category"])
        gold = preprocess_answer(category, str(record["gold"]))
        metrics = categories[category]
        metrics["n"] += 1
        metrics["correct"] += float(record.get("J", 0.0))
        metrics["f1"] += token_f1(str(record.get("answer", "")), gold)
        metrics["bleu1"] += bleu1(str(record.get("answer", "")), gold)
        gold_evidence = set(record.get("gold_evidence") or [])
        if gold_evidence:
            metrics["evidence_recall"] += len(
                gold_evidence & set(record.get("pack_src") or [])
            ) / len(gold_evidence)
            metrics["evidence_n"] += 1

    def finish(values: dict) -> dict:
        n = int(values["n"])
        return {
            "n": n,
            "accuracy": values["correct"] / n if n else 0.0,
            "f1": values["f1"] / n if n else 0.0,
            "bleu1": values["bleu1"] / n if n else 0.0,
            "evidence_recall": (
                values["evidence_recall"] / values["evidence_n"] if values["evidence_n"] else None
            ),
        }

    total = collections.defaultdict(float)
    by_category = {}
    for category, values in sorted(categories.items()):
        by_category[CATEGORIES[category]] = finish(values)
        for key, value in values.items():
            total[key] += value
    return {"overall": finish(total), "categories": by_category}
