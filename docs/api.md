# Memory API

The v0.1 application API has one active object, `Memory`, and two returned
values: `Fact` and `Answer`.

```python
from memoket_kite import Memory

memory = Memory.load("memory.xml")
memory.remember(
    [
        {"role": "alice", "content": "I enjoy trail running."},
        {"role": "bob", "content": "Alice has a race in October."},
    ],
    session_id="july-chat",
    date="2026-07-29",
    title="July catch-up",
)

facts = memory.recall("What does Alice enjoy?")
for fact in facts:
    print(fact.content)
    print(fact.topics)
    for source in fact.sources:
        print(source["role"], source["content"])

result = memory.answer_with_evidence("What does Alice enjoy?")
print(result.text)
print(result.citations)
```

## Load

`Memory.load(source)` loads one XML file or a sequence of XML shards. Advanced
callers may override `model`, `answer_model`, and `reference_date` as
keyword-only parameters. Loading XML is offline; provider configuration is
checked when an operation needs an LLM.

## Experimental remember

`remember(messages, *, session_id=None, date=None, title=None,
include_facets=True)` accepts a non-empty sequence of
`{ "role": ..., "content": ... }` mappings or `(role, content)` tuples. The
default extraction prompt returns each Fact together with its object, place,
event, and duration facets in the same model call. It returns the extracted
`list[Fact]` and atomically updates one XML artifact.

These facets are persisted in the existing XML facet attributes and are
available on returned Facts through `fact.metadata["objects"]`,
`fact.metadata["places"]`, `fact.metadata["events"]`, and
`fact.metadata["duration"]`.

Set `include_facets=False` to run facet-free extraction for ablation. In that
mode the prompt does not request facet fields and any unexpected facet fields
in the model response are discarded. `remember()` does not support multiple
writable shards, concurrent writers, or conflict resolution.


## Recall

`recall(query, *, limit=10)` returns `list[Fact]`. A Fact exposes its structured
kind, subject, topics, entities, event/source times, confidence, and supporting
utterances. Sources are read-only mappings with `id`, `role`, `content`, and
`date`.

Only facts are returned. Retrieval may also surface raw conversation lines and
session records; those are not facts and are never dressed up as one — they
stay visible as each fact's `sources`. Query plans and execution traces remain
available only through the research API.

## Answer

`answer(question, *, limit=10)` returns a string.

`answer_with_evidence(question, *, limit=10)` returns an `Answer`: the same
text, plus `evidence` (the recalled `Fact`s the reader was shown) and
`citations` (the provenance IDs the reader cited). An ID can name a Fact, a raw
conversation line, or a deduplicated instance that was rendered in the bounded
evidence pack. Raw lines and instances do not appear in the Fact-only
`evidence` tuple. Evidence is the retrieved basis for the answer, not a proof
of it — the reader chose its words; the evidence shows what it saw.

## Errors

Every public failure derives from `KiteError`. Specific configuration,
storage, provider, and query subclasses exist for callers that need to
distinguish them. The library never raises Python's built-in `MemoryError`,
and deliberately defines no name that shadows it.
