# Codebook format

KITE persists symbolic memory as XML. XML is the serialization format;
`Memory.load` builds the in-memory indexes used for symbolic retrieval.

```xml
<codebook id="demo" speakers="alice bob">
  <vocab>
    <topic code="travel" status="canonical" parents="" born="" />
    <entity code="kyoto" type="place" name="Kyoto" />
  </vocab>
  <timeline>
    <session id="s1" date="2026-01-10">
      <fact id="s1F1"
            kind="plan"
            who="alice"
            conf="high"
            topics="travel"
            entities="kyoto"
            src="s1L1">Alice plans to visit Kyoto in April.</fact>
      <line id="s1L1" who="alice">I will visit Kyoto in April.</line>
    </session>
  </timeline>
</codebook>
```

`<topic>` and `<entity>` entries sit directly under `<vocab>` — the parser
reads them as flat children, so a wrapper element would be silently ignored. A
complete worked example lives at
[`examples/data/demo_codebook.xml`](../examples/data/demo_codebook.xml).

Each `<fact>` is a structured memory primitive. Important Fact attributes:

- `id`: stable fact identifier.
- `t`: event time when known; the parent unit date remains source time.
- `kind`: profile-defined fact category.
- `who`: normalized subject.
- `conf`: extraction confidence.
- `topics` and `entities`: controlled symbolic codes.
- `obj`, `place`, `event`, `dur`: optional parallel facets.
- `src`: original line IDs supporting the fact.

The format is managed by `Memory.remember` during the alpha period. Advanced
research users can inspect it through `memoket_kite.research.Codebook`; its
round-trip behavior is covered by offline regression tests.
