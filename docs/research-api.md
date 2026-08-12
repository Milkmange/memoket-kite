# Research API

The `memoket_kite.research` module retains KITE's advanced artifact and
symbolic-query interfaces for benchmark reproduction and algorithm research.
Applications should use `Memory` instead.

```python
from memoket_kite.research import Codebook, QueryPlan

book = Codebook.load("memory.xml")
result = book.execute(
    QueryPlan.from_dict(
        {
            "queries": [{"select": "facts", "where": {"grep": "marathon"}}],
            "intent": "factual",
        }
    )
)
```

`Codebook`, `Reasoner`, `SymbolicQuery`, `QueryPlan`, profiles, and their
result types are research interfaces. They remain useful for inspecting plans
and reproducing experiments, but are not the stable application API.
