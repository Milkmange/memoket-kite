"""Prompt templates for evidence-backed answer generation and verification."""

DEFAULT_ATTRIBUTION_ANSWER = "Likely {who}, based on: '{quote}'"

DEFAULT_ANSWER_PROMPT = """Answer using only the supplied evidence. If it is insufficient, say so.
TODAY: {today}
QUESTION: {question}
POLICIES:
{policies}
EVIDENCE:
{evidence}
Return JSON only: {{"answer":str,"evidence":[provenance_id]}}"""

KERNEL_POLICIES = """- Ground every claim in the evidence rows. Cite only provenance IDs
  visibly printed in the evidence: Fact IDs, raw-line IDs, or instance IDs.
- Dates in your answer must be COPIED VERBATIM from evidence row headers —
  never adjust, infer, or invent a date.
- Rows marked [anchored] were retrieved FROM THE SPECIFIC meeting/event the
  question refers to. When the question is about that meeting ("at the X
  meeting", "after the X meeting"), answer from [anchored] rows; other rows
  are context from OTHER conversations — do not confuse them even if their
  wording matches the question more literally.
- [aggregate] rows are authoritative computed results over the FULL corpus.
  For counting/how-many questions, answer with the aggregate value verbatim;
  NEVER count the evidence rows yourself (they are a truncated sample).
- Evidence is chronological. When rows CONTRADICT, the most recent wins;
  for enumerations, union across all time.
- Factual questions: if the asked detail is stated nowhere in the evidence,
  reply exactly: {refusal}
- CHECK THE QUESTION'S PRESUPPOSITIONS: if the question attributes an object,
  event, or statement to person X but the evidence shows it belongs to a
  DIFFERENT person, that is a trap — reply exactly: {refusal}
  (e.g. "What does A's necklace symbolize?" when the necklace is B's).
- Speculative/judgment questions (would/could/might/likely): NEVER refuse;
  infer from the evidence (recency-weighted). Absence of the trait = "Likely no".
- Relative time in evidence: resolve month/year level ("next month" in a
  [2023-05-25] row = June 2023); do NOT do day-of-week arithmetic — answer
  relative to the row date ("the Sunday before 25 May 2023"). If a row pairs a
  weekday phrase with a computed date, distrust the computation and answer with
  the relative phrase."""

REFUSAL = "No information"

# Round-2 feedback retrieval: the model sees ONLY the system's own first-round
# evidence (never gold) and names what is missing.
REFINE_PROMPT = """A first retrieval round produced the evidence below for this question,
but the drafted answer ("{draft}") appears unsupported or unspecific.

QUESTION: {question}

FIRST-ROUND EVIDENCE:
{evidence}

State what the evidence visibly fails to cover about the question, then give
search terms for a second retrieval round:
- 2-5 short terms, each a concrete noun/verb/name likely to appear VERBATIM
  in the missing conversation turns (think: how would the speakers have
  actually phrased it?).
- Prefer specific candidates over categories (for "which brand" list plausible
  brand names; for "how celebrated" list party/relax/dinner).
Return ONLY JSON: {{"gap": str, "terms": [str]}}"""

SUPPORT_CHECK_PROMPT = """QUESTION: {question}
ANSWER GIVEN: {answer}

EVIDENCE:
{evidence}

Does at least one evidence row actually STATE the core fact claimed in the answer (not merely a related topic)? Be strict: paraphrase counts, but topical similarity without the specific fact does not. Return ONLY JSON: {{"supported": true/false}}"""

SELF_CONSISTENCY_PICK_PROMPT = """Several independent attempts answered the same question from the same evidence. Pick the answer most consistent with the majority reasoning — prefer the one whose content the other attempts agree with, not merely the longest.

QUESTION: {question}

ATTEMPTS:
{attempts}

Return ONLY JSON: {{"pick": <attempt number>}}"""
