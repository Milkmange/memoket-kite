"""Prompt templates for fact extraction and facet assignment."""

_FACT_EXTRACTION_BASE_PROMPT = """Extract durable, atomic structured facts from this conversation.
SESSION DATE: {date}
SPEAKERS: {speakers}
KNOWN TOPICS: {tree}
KNOWN ENTITIES: {entities}
CONVERSATION (id|speaker|time|text):
{dialog}

Rules:
- Capture durable information that may matter in a later conversation. Write
  one self-contained claim per fact; do not infer information not stated.
- "kind": one of {kinds}. "who": the person or role the fact is about.
- "t": event time as YYYY-MM-DD or YYYY-MM when stated or safely resolvable;
  otherwise null. "conf": high, med, or low.
- "topics": reuse the most specific known codes. If none fits, propose one
  specific child under a known root. "entities": named people, places,
  organizations, products, works, or other concrete named things.
- "src": one or more message IDs that directly support the fact.
"""

DEFAULT_EXTRACT_PROMPT = (
    _FACT_EXTRACTION_BASE_PROMPT
    + """
Add retrieval facets to each fact without creating extra facts:
- "object": up to four singular common-noun classes for concrete things discussed
  (for example, "dog" rather than a pet's name); use [] when none applies.
- "place": specific named places stated in the fact; use [] when absent.
- "event": only values from this allowed set: {events}; use [] when none applies.
- "duration": a duration explicitly stated in the fact, encoded as ISO-8601
  (for example P3Y, P2W, or P6M); use null when absent.

Return JSON only:

{{
  "facts": [
    {{
      "content": str,
      "kind": one of {kinds},
      "who": str,
      "t": str | null,
      "conf": "high|med|low",
      "topics": [str],
      "entities": [str],
      "src": [str],
      "facets": {{
        "object": [str],
        "place": [str],
        "event": [str],
        "duration": str | null
      }}
    }}
  ],
  "proposals": [
    {{
      "code": str,
      "parent": str
    }}
  ],
  "entity_types": {{}}
}}"""
)

DEFAULT_EXTRACT_PROMPT_NO_FACETS = (
    _FACT_EXTRACTION_BASE_PROMPT
    + """
Return JSON only:
{{
  "facts": [
    {{
      "content": str,
      "kind": one of {kinds},
      "who": str,
      "t": str | null,
      "conf": "high|med|low",
      "topics": [str],
      "entities": [str],
      "src": [str]
    }}
  ],
  "proposals": [
    {{
      "code": str,
      "parent": str
    }}
  ],
  "entity_types": {{}}
}}"""
)


TOPIC_CONSOLIDATION_PROMPT = """You maintain the controlled topic taxonomy for a
long-term conversational memory. For each pair of topic codes, decide whether
they denote exactly the same conversational subject.

Merge only true synonyms, spelling variants, or equivalent phrasings. Do not
merge a broad topic with one of its subtopics, a whole with one of its parts, or
two subjects that are merely related. Preserve distinctions that would help a
later retrieval request identify the right conversation. When merging, choose
the clearer, more specific code that remains understandable on its own.

TOPIC PAIRS:
{pairs}

Return JSON only:
{{"decisions": [{{"i": 0, "merge": true, "winner": str}}]}}"""


ENTITY_CONSOLIDATION_PROMPT = """You maintain the entity registry for a
long-term conversational memory. For each pair of entity codes, decide whether
they refer to the same real-world person, organization, place, product, work,
or named object.

Merge only aliases, spelling variants, abbreviations, nicknames, or full and
short forms of the same entity. Do not merge entities that are merely related,
mentioned together, similar in name, or different versions/models. When
merging, choose the clearest canonical code from the pair.

ENTITY PAIRS:
{pairs}

Return JSON only:
{{"decisions": [{{"i": 0, "merge": true, "winner": str}}]}}"""


INSTANCE_ALIGNMENT_PROMPT = """You are aligning repeated Fact mentions in a
symbolic memory Codebook. For each cluster, group IDs that identify the same
distinct real-world object, event, purchase, trip, project, or activity.

- Combine mentions of the same instance across conversation sessions.
- Keep distinct items or events separate, even in the same turn.
- Omit abstract states, advice, questions, and other non-countable mentions.
- Give each retained instance a short, specific label and one kind: object |
  event | expense | trip | activity | other.

{clusters}

Return only JSON:
{{
  "clusters": [{{
    "n": <cluster number>,
    "instances": [{{"label": str, "kind": str, "ids": [str]}}]
  }}]
}}"""
