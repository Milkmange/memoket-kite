"""Official LongMemEval typed judge prompts and aggregate metrics."""

from __future__ import annotations

import collections

JUDGE_PROMPTS = {
    "default": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. \n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "temporal-reasoning": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct. \n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "knowledge-update": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.\n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "single-session-preference": "I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.\n\nQuestion: {q}\n\nRubric: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "abstention": "I will give you an unanswerable question, an explanation, and a response from a model. Please answer yes if the model correctly identifies the question as unanswerable. The model could say that the information is incomplete, or some other information is given but the asked information is not.\n\nQuestion: {q}\n\nExplanation: {a}\n\nModel Response: {r}\n\nDoes the model correctly identify the question as unanswerable? Answer yes or no only.",
}


def question_type(record: dict) -> str:
    return "abstention" if "_abs" in str(record["question_id"]) else record["question_type"]


def summarize(records: list[dict]) -> dict:
    """Compute accuracy and evidence recall from judged result rows."""
    groups = collections.defaultdict(lambda: collections.defaultdict(float))
    for record in records:
        metrics = groups[question_type(record)]
        metrics["n"] += 1
        metrics["correct"] += float(record.get("ok", 0.0))
        gold_sessions = set(record.get("answer_session_ids") or [])
        if gold_sessions:
            metrics["evidence_recall"] += len(
                gold_sessions & set(record.get("pack_units") or [])
            ) / len(gold_sessions)
            metrics["evidence_n"] += 1

    def finish(values: dict) -> dict:
        n = int(values["n"])
        return {
            "n": n,
            "accuracy": values["correct"] / n if n else 0.0,
            "evidence_recall": (
                values["evidence_recall"] / values["evidence_n"] if values["evidence_n"] else None
            ),
        }

    total = collections.defaultdict(float)
    by_type = {}
    for name, values in sorted(groups.items()):
        by_type[name] = finish(values)
        for key, value in values.items():
            total[key] += value
    return {"overall": finish(total), "question_types": by_type}
