# Method

KITE is a symbolic episodic memory method for long-term conversational agents.
Its basic memory unit is a structured Fact supported by one or more original
utterances. A Codebook combines those Facts with their conversation sessions,
controlled topic and entity vocabularies, temporal fields, and deterministic
indexes.

## Build a Codebook

For each conversation episode, KITE performs the following stages:

1. **Fact extraction.** An LLM converts substantive utterances into atomic,
   self-contained Facts. Each Fact records its subject, kind, confidence,
   source IDs, event time when available, topics, entities, and retrieval
   facets. A facet-free extraction mode is retained for ablation.
2. **Vocabulary admission.** Existing topic and entity codes are reused;
   proposed codes enter the controlled vocabulary through deterministic
   normalization and admission rules.
3. **Vocabulary consolidation.** Equivalent topic and entity codes are merged
   conservatively, and affected Fact references are rewritten consistently.
4. **Codebook finalization.** Benchmark profiles may enable corpus-level build
   stages that require a complete Codebook. Cleaned LongMemEval enables global
   instance alignment for distinct-item enumeration and topic-assignment
   refinement against the completed taxonomy. These stages run uniformly for
   every Codebook before it is atomically published; they are not query-time
   post-processing.

## Retrieve evidence

A natural-language question is compiled into a symbolic plan containing one or
more structured subqueries. Plans may be parallel or staged when a later query
depends on the units or dates found by an earlier query.

The retrieval pipeline then:

1. validates and normalizes the plan against the Codebook;
2. evaluates topic, entity, kind, speaker, time, and text-pattern constraints;
3. records any deterministic relaxation or repair;
4. combines symbolic and lexical candidates;
5. selects an ordered evidence pack under a fixed budget.

With a fixed Codebook and plan, this procedure is deterministic. The trace
records the decisions needed to inspect or replay it.

## Produce an evidence-backed answer

The answer pipeline hydrates retrieved Facts with their original source lines
and relevant temporal or instance context. Deterministic attribution and
aggregate cases may be answered directly. Other questions are answered by an
LLM from the bounded evidence pack, with every cited Fact, source-line, or
instance ID checked against provenance actually visible to the reader. Bounded
recovery passes can request additional evidence when the initial answer is
unsupported or incomplete.

KITE exposes the symbolic plan, evidence, and execution trace as its auditable
reasoning record. It does not expose or require model chain-of-thought.

## Scope

KITE is not a knowledge graph system, database, generic RAG framework, or
general reasoning engine. It focuses on structured episodic memory for
conversation: preserving what was said, when it happened, how it was indexed,
why it was retrieved, and which evidence supports the answer.
