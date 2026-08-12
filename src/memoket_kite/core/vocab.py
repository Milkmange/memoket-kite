"""Core governed vocabulary for the Codebook symbolic memory representation.

Topics form a DAG taxonomy with a lifecycle (candidate -> canonical -> deprecated).
Entities form a registry with aliases and typed relations. Conversation speakers
belong to the loaded Store rather than this governed vocabulary.
All mutation goes through operators that enforce invariants; growth is bounded
by governance triggers (admission / promotion / consolidation / deprecation).

Pure symbolic layer: no LLM, no I/O besides XML (de)serialization.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


def norm_code(x: str) -> str:
    s = str(x).strip().lower()
    return re.sub(r"[^\w一-鿿]+", "_", s).strip("_")


class VocabError(ValueError):
    pass


@dataclass
class Topic:
    code: str
    parents: set = field(default_factory=set)
    status: str = "candidate"  # candidate | canonical | deprecated
    aliases: set = field(default_factory=set)
    born: str = ""  # unit id that proposed it
    usage: dict = field(default_factory=dict)  # unit_id -> time_bucket


@dataclass
class Entity:
    code: str
    etype: str = ""  # e.g. person / org.supplier / product
    name: str = ""
    aliases: set = field(default_factory=set)
    rels: set = field(default_factory=set)  # {(rel_type, other_code)}


class Vocab:
    def __init__(self, admission_k: int = 5, promote_units: int = 3):
        self.topics: dict[str, Topic] = {}
        self.entities: dict[str, Entity] = {}
        self._alias_t: dict[str, str] = {}  # surface -> topic code
        self._alias_e: dict[str, str] = {}
        self.admission_k = admission_k
        self.promote_units = promote_units
        self.oplog: list[str] = []

    # ---------------- resolution ----------------
    def resolve_topic(self, surface: str) -> str | None:
        s = norm_code(surface)
        if s in self.topics and self.topics[s].status != "deprecated":
            return s
        return self._alias_t.get(s)

    def resolve_entity(self, surface: str) -> str | None:
        s = norm_code(surface)
        if s in self.entities:
            return s
        return self._alias_e.get(s)

    # ---------------- taxonomy queries ----------------
    def children(self, code: str) -> set[str]:
        return {c for c, t in self.topics.items() if code in t.parents}

    def downset(
        self, code: str, max_depth: int = 3, max_width: int = 40, include_candidates: bool = False
    ) -> set[str]:
        """Return ``code`` and a deterministically bounded descendant closure.

        ``max_width`` includes the root. An existing root is always returned,
        even when callers provide a non-positive width.
        """
        if code not in self.topics:
            return set()
        max_width = max(1, max_width)
        out, frontier = {code}, {code}
        for _ in range(max_depth):
            nxt = set()
            for c in sorted(frontier):
                for ch in sorted(self.children(c)):
                    t = self.topics[ch]
                    if t.status == "deprecated":
                        continue
                    if t.status == "candidate" and not include_candidates:
                        continue
                    if ch not in out:
                        nxt.add(ch)
            remaining = max_width - len(out)
            if remaining <= 0:
                break
            frontier = set(sorted(nxt)[:remaining])
            out.update(frontier)
            if len(frontier) < len(nxt):
                break
            if not frontier:
                break
        return out

    def related(self, ecode: str, rel_types: set[str] | None = None) -> set[str]:
        e = self.entities.get(ecode)
        if not e:
            return set()
        out = set()
        for rel, other in e.rels:
            if rel_types is None or rel in rel_types:
                out.add(other)
        for other_code, other in self.entities.items():
            for rel, tgt in other.rels:
                if tgt == ecode and (rel_types is None or rel in rel_types):
                    out.add(other_code)
        return out

    # ---------------- operators ----------------
    def define_root(self, code: str):
        code = norm_code(code)
        if code in self.topics:
            return code
        self.topics[code] = Topic(code, status="canonical")
        self.oplog.append(f"define_root {code}")
        return code

    def propose_topic(self, code: str, parent: str, unit: str, bucket: str = "") -> str | None:
        """Admission-controlled candidate creation. Returns resolved code or None."""
        code, parent = norm_code(code), norm_code(parent)
        if not code:
            # from_xml refuses an empty code in both strict and lenient mode;
            # the writer must enforce the same invariant or it writes a file
            # that can never be read back.
            return None
        existing = self.resolve_topic(code)
        if existing:
            self.touch_topic(existing, unit, bucket)
            return existing
        pcode = self.resolve_topic(parent)
        if not pcode:
            return None  # orphan proposals are rejected
        admitted_this_unit = sum(1 for t in self.topics.values() if t.born == unit)
        if admitted_this_unit >= self.admission_k:
            self.touch_topic(pcode, unit, bucket)
            return pcode  # over budget -> fold into parent
        self.topics[code] = Topic(code, parents={pcode}, born=unit, usage={unit: bucket})
        self.oplog.append(f"propose {code} < {pcode} @{unit}")
        return code

    def touch_topic(self, code: str, unit: str, bucket: str = ""):
        if code in self.topics:
            self.topics[code].usage[unit] = bucket

    def alias_topic(self, surface: str, code: str):
        s, code = norm_code(surface), norm_code(code)
        if code not in self.topics:
            raise VocabError(f"alias target missing: {code}")
        if s != code:
            self.topics[code].aliases.add(s)
            self._alias_t[s] = code
            self.oplog.append(f"alias {s} -> {code}")

    def promote(self, code: str):
        t = self.topics[code]
        t.status = "canonical"
        self.oplog.append(f"promote {code}")

    def merge_topics(self, losers: list[str], winner: str) -> dict[str, str]:
        """Merge codes into winner. Returns rewrite map for the store to apply."""
        winner = norm_code(winner)
        if winner not in self.topics:
            raise VocabError(f"merge winner missing: {winner}")
        rewrite = {}
        for lo in losers:
            lo = norm_code(lo)
            if lo == winner or lo not in self.topics:
                continue
            t = self.topics[lo]
            # children re-parent to winner
            for ch in self.children(lo):
                self.topics[ch].parents.discard(lo)
                self.topics[ch].parents.add(winner)
            self.topics[winner].usage.update(t.usage)
            for a in t.aliases | {lo}:
                self.topics[winner].aliases.add(a)
                self._alias_t[a] = winner
            del self.topics[lo]
            rewrite[lo] = winner
            self.oplog.append(f"merge {lo} -> {winner}")
        self._assert_acyclic()
        return rewrite

    def move_topic(self, code: str, new_parents: list[str]):
        code = norm_code(code)
        ps = {norm_code(p) for p in new_parents}
        missing = [p for p in ps if p not in self.topics]
        if missing:
            raise VocabError(f"move parents missing: {missing}")
        old = self.topics[code].parents
        self.topics[code].parents = ps
        try:
            self._assert_acyclic()
        except VocabError:
            self.topics[code].parents = old
            raise
        self.oplog.append(f"move {code} -> {sorted(ps)}")

    def deprecate_topic(self, code: str):
        code = norm_code(code)
        for ch in self.children(code):
            self.topics[ch].parents |= self.topics[code].parents
            self.topics[ch].parents.discard(code)
        self.topics[code].status = "deprecated"
        self.oplog.append(f"deprecate {code}")

    def register_entity(self, surface: str, etype: str = "") -> str:
        code = self.resolve_entity(surface) or norm_code(surface)
        if not code:
            raise VocabError(f"entity code must be non-empty: {surface!r}")
        if code not in self.entities:
            self.entities[code] = Entity(code, etype=etype, name=str(surface).strip())
        if etype and not self.entities[code].etype:
            self.entities[code].etype = etype
        return code

    def alias_entity(self, surface: str, code: str):
        s = norm_code(surface)
        if code not in self.entities:
            raise VocabError(f"alias target missing: {code}")
        if s != code:
            self.entities[code].aliases.add(s)
            self._alias_e[s] = code

    def merge_entities(self, losers: list[str], winner: str) -> dict[str, str]:
        rewrite = {}
        for lo in losers:
            lo = norm_code(lo)
            if lo == winner or lo not in self.entities:
                continue
            e = self.entities[lo]
            w = self.entities[winner]
            w.aliases |= e.aliases | {lo}
            w.rels |= e.rels
            for a in e.aliases | {lo}:
                self._alias_e[a] = winner
            del self.entities[lo]
            rewrite[lo] = winner
            self.oplog.append(f"merge_entity {lo} -> {winner}")
        return rewrite

    def relate(self, a: str, rel: str, b: str):
        if a not in self.entities or b not in self.entities:
            raise VocabError(f"relate: unknown entity {a} or {b}")
        self.entities[a].rels.add((rel, b))
        self.oplog.append(f"relate {a} -{rel}-> {b}")

    # ---------------- governance triggers ----------------
    def promotion_pass(self) -> list[str]:
        out = []
        for c, t in self.topics.items():
            if (
                t.status == "candidate"
                and len(t.usage) >= self.promote_units
                and len(set(t.usage.values())) >= 2
            ):
                self.promote(c)
                out.append(c)
        return out

    def consolidation_pressure(self, pool_max: int = 60) -> bool:
        return sum(1 for t in self.topics.values() if t.status == "candidate") > pool_max

    def consolidation_candidates(self, min_shared: int = 2) -> list[tuple[str, str]]:
        """Deterministic merge *proposals* (adjudication happens outside):
        candidate pairs sharing a parent whose usage co-occurs in >= min_shared
        units, or whose codes are prefix/suffix variants."""
        pairs = []
        cands = [t for t in self.topics.values() if t.status == "candidate"]
        by_parent: dict[str, list[Topic]] = {}
        for t in cands:
            for p in t.parents:
                by_parent.setdefault(p, []).append(t)
        seen = set()
        for group in by_parent.values():
            for i, a in enumerate(group):
                for b in group[i + 1 :]:
                    key = tuple(sorted((a.code, b.code)))
                    if key in seen:
                        continue
                    shared = len(set(a.usage) & set(b.usage))
                    affix = (
                        a.code.startswith(b.code)
                        or b.code.startswith(a.code)
                        or a.code.endswith(b.code)
                        or b.code.endswith(a.code)
                    )
                    if shared >= min_shared or affix:
                        seen.add(key)
                        pairs.append(key)
        return pairs

    def entity_merge_candidates(self, min_len: int = 2) -> list[tuple[str, str]]:
        """Deterministic alias-merge proposals: containment or hamming-1 pairs.

        A transcription of the same name twice can differ by one character, so
        near-identical codes are proposed for merging; adjudication happens
        outside. Guardrail: codes containing digits are VALUES (prices, model
        numbers, durations), where a one-character difference changes the fact
        rather than spelling it differently, so those never merge."""
        codes = [c for c in self.entities if len(c) >= min_len and not re.search(r"\d", c)]
        pairs = []
        for i, a in enumerate(codes):
            for b in codes[i + 1 :]:
                if a in b or b in a:
                    # Containment: a generic short word must not be swallowed
                    # by a specific name that contains it ("motor" inside
                    # "quiet motor"), so the shorter side needs >= 3 characters
                    # before the pair is proposed at all.
                    if min(len(a), len(b)) >= 3:
                        pairs.append((a, b))
                elif len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1:
                    pairs.append((a, b))
        return pairs

    # ---------------- invariants ----------------
    def _assert_acyclic(self):
        color: dict[str, int] = {}

        def visit(c):
            color[c] = 1
            for p in sorted(self.topics[c].parents):
                if p in self.topics:
                    if color.get(p) == 1:
                        raise VocabError(f"taxonomy cycle at {p}")
                    if color.get(p, 0) == 0:
                        visit(p)
            color[c] = 2

        for c in sorted(self.topics):
            if color.get(c, 0) == 0:
                visit(c)

    def check(self) -> list[str]:
        problems = []
        try:
            self._assert_acyclic()
        except VocabError as e:
            problems.append(str(e))
        for c, t in sorted(self.topics.items()):
            for p in sorted(t.parents):
                if p not in self.topics:
                    problems.append(f"missing parent {p} of {c}")
            if t.status != "deprecated" and not t.parents and t.status == "candidate":
                problems.append(f"orphan candidate {c}")
        for s, c in sorted(self._alias_t.items()):
            if c not in self.topics:
                problems.append(f"dangling topic alias {s}->{c}")
            if s in self.topics:
                problems.append(f"topic alias conflicts with topic code {s}")
        for s, c in sorted(self._alias_e.items()):
            if c not in self.entities:
                problems.append(f"dangling entity alias {s}->{c}")
            if s in self.entities:
                problems.append(f"entity alias conflicts with entity code {s}")
        for c, entity in sorted(self.entities.items()):
            for rel, target in sorted(entity.rels):
                if target not in self.entities:
                    problems.append(f"missing entity relation target {target} of {c} ({rel})")
        return problems

    # ---------------- stats & rendering ----------------
    def render_tree(self, max_lines: int = 200, include_candidates: bool = True) -> str:
        """Compact indented rendering for LLM prompts."""
        roots = sorted(
            c for c, t in self.topics.items() if not t.parents and t.status != "deprecated"
        )
        lines: list[str] = []

        def walk(code, depth):
            if len(lines) >= max_lines:
                return
            t = self.topics[code]
            if t.status == "deprecated":
                return
            if t.status == "candidate" and not include_candidates:
                return
            mark = "?" if t.status == "candidate" else ""
            lines.append("  " * depth + code + mark)
            for ch in sorted(self.children(code)):
                walk(ch, depth + 1)

        for r in roots:
            walk(r, 0)
        return "\n".join(lines)

    # ---------------- persistence ----------------
    def to_xml(self) -> ET.Element:
        el = ET.Element("vocab")
        for c in sorted(self.topics):
            t = self.topics[c]
            te = ET.SubElement(
                el,
                "topic",
                code=c,
                status=t.status,
                parents=" ".join(sorted(t.parents)),
                born=t.born,
            )
            for a in sorted(t.aliases):
                ET.SubElement(te, "alias").text = a
            for u, b in sorted(t.usage.items()):
                ET.SubElement(te, "use", unit=str(u), bucket=str(b))
        for c in sorted(self.entities):
            e = self.entities[c]
            ee = ET.SubElement(el, "entity", code=c, type=e.etype, name=e.name)
            for a in sorted(e.aliases):
                ET.SubElement(ee, "alias").text = a
            for rel, other in sorted(e.rels):
                ET.SubElement(ee, "rel", type=rel, to=other)
        return el

    @classmethod
    def from_xml(cls, el: ET.Element, *, strict: bool = False, **kw) -> "Vocab":
        """Deserialize a vocabulary.

        The default mode tolerates soft taxonomy inconsistencies — an
        unnormalised code, a parent that no topic defines, an alias whose
        surface is also a concrete topic code — because each of those still
        names exactly one symbol, so resolution and the downset traversal
        remain well defined.  ``strict=True`` additionally runs :meth:`check`
        and rejects them, which is the guarantee a builder or a migration tool
        wants for an artifact it has just produced.

        Structural ambiguity is refused in both modes: an empty or duplicate
        symbol, a malformed alias, or an invalid status, use, or relation has
        no single correct reading, so there is nothing to fall back to.
        """

        def required_code(raw: str | None, label: str) -> str:
            value = (raw or "").strip()
            if not value:
                raise VocabError(f"{label} code must be non-empty")
            if strict and (value != raw or value != norm_code(value)):
                raise VocabError(f"{label} code must be normalized: {raw!r}")
            return value

        def alias_surface(alias: ET.Element, label: str) -> str:
            raw = alias.text
            if not raw or not raw.strip():
                raise VocabError(f"{label} alias text must be non-empty")
            surface = norm_code(raw)
            if not surface:
                raise VocabError(f"{label} alias text must contain a symbol")
            return surface

        def register_alias(aliases: dict[str, str], surface: str, target: str, label: str) -> None:
            if not target:
                raise VocabError(f"{label} alias target must be non-empty")
            if surface in aliases:
                raise VocabError(f"duplicate {label} alias: {surface}")
            aliases[surface] = target

        v = cls(**kw)
        for te in el.findall("topic"):
            c = required_code(te.get("code"), "Topic")
            if c in v.topics:
                raise VocabError(f"duplicate Topic code: {c}")
            status = te.get("status", "canonical")
            if status not in {"candidate", "canonical", "deprecated"}:
                raise VocabError(f"invalid Topic status for {c}: {status!r}")
            parents = {
                required_code(parent, f"Topic parent of {c}")
                for parent in (te.get("parents") or "").split()
            }
            t = Topic(
                c,
                parents=parents,
                status=status,
                born=te.get("born", ""),
            )
            for a in te.findall("alias"):
                surface = alias_surface(a, "Topic")
                register_alias(v._alias_t, surface, c, "Topic")
                t.aliases.add(surface)
            for u in te.findall("use"):
                unit = (u.get("unit") or "").strip()
                if not unit:
                    raise VocabError(f"Topic use unit must be non-empty: {c}")
                if unit in t.usage:
                    raise VocabError(f"duplicate Topic use unit for {c}: {unit}")
                t.usage[unit] = u.get("bucket", "")
            v.topics[c] = t
        for ee in el.findall("entity"):
            c = required_code(ee.get("code"), "Entity")
            if c in v.entities:
                raise VocabError(f"duplicate Entity code: {c}")
            e = Entity(c, etype=ee.get("type", ""), name=ee.get("name", ""))
            for a in ee.findall("alias"):
                surface = alias_surface(a, "Entity")
                register_alias(v._alias_e, surface, c, "Entity")
                e.aliases.add(surface)
            for r in ee.findall("rel"):
                rel = (r.get("type") or "").strip()
                if not rel:
                    raise VocabError(f"Entity relation type must be non-empty: {c}")
                target = required_code(r.get("to"), f"Entity relation target of {c}")
                relation = (rel, target)
                if relation in e.rels:
                    raise VocabError(f"duplicate Entity relation for {c}: {rel}->{target}")
                e.rels.add(relation)
            v.entities[c] = e

        if strict:
            problems = v.check()
            if problems:
                raise VocabError("invalid vocabulary: " + "; ".join(problems))
        return v
