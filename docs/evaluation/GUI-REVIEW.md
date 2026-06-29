# GUI Assessment — UX Design Review

> Honest evaluation of the current session viewer and gallery against the
> six functional goals from `value-proposition.md`.
> Written from the perspective of a commercial GUI/UX designer.

---

## Current State: What Exists

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: Gallery (index.html)                                  │
│  Card grid of sessions. Click → opens session viewer.           │
│  No search. No cross-session view. No knowledge base.           │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: Session Viewer (session-view.html)                    │
│  Phase timeline + turn cards + label filters + search           │
│  Works for ONE session at a time.                               │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: Extracted Notes (zettel .md files)                    │
│  YAML frontmatter + markdown body. No viewer. No linking UI.    │
│  Files sit on disk. User must open them manually.               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Goal-by-Goal Assessment

### Goal 1: Recall Across Chats

> *"Find a specific insight without remembering which conversation it was in."*

**Current GUI:** ❌ Not served.

The gallery shows session cards sorted by score. There is no search box that
spans all sessions. If you remember "we discussed connection pooling," you
must click through each session viewer and search individually.

**What's needed:**

```
┌─────────────────────────────────────────────────────────────┐
│  🔍 Search across all sessions...                    [⌘K]   │
├─────────────────────────────────────────────────────────────┤
│  Results for "connection pooling":                           │
│                                                             │
│  📄 kuchnie/019efb69 · Turn 45 · [Pragmatic, Warning]      │
│     "For connection pooling in SQLAlchemy, use pool_size..." │
│                                                             │
│  📄 git-llm/019f0b65 · Turn 153 · [Analytical, Pragmatic]  │
│     "The DB pool exhaustion bug happens when..."             │
│                                                             │
│  📝 Knowledge note: "Connection pooling patterns"           │
│     Extracted from kuchnie/019efb69 · linked to 2 sessions   │
└─────────────────────────────────────────────────────────────┘
```

**Design principle:** *Recognition over recall.* The user should type what
they remember, not where they remember it from.

---

### Goal 2: Navigate Within a Chat

> *"Skim a 40-turn discussion in 60 seconds and jump to the part that matters."*

**Current GUI:** ✅ Well served.

The phase timeline in the left sidebar is the primary navigation. Clicking a
phase scrolls to it. Turn cards are compact (role + labels + char count) and
expandable. Thinking blocks and tool-use turns are hidden by default.

**What's working:**
- Phase timeline with color-coded states (ACTION, EVALUATION, EXPLORATION)
- Sticky phase headers that stay visible while scrolling
- Turn cards show enough metadata to skip without reading
- Label badges give instant context

**What could improve:**
- Phase summaries should be visible in the sidebar (currently just state + range)
- A "minimap" scrollbar showing turn density and phase boundaries
- Keyboard shortcuts (j/k to navigate turns, Enter to expand)

**Design principle:** *Progressive disclosure.* Overview first, details on demand.

---

### Goal 3: Separate Signal from Noise

> *"Hide tangents, dead ends, and abandoned branches without deleting them."*

**Current GUI:** ⚠️ Partially served.

The thinking/tool toggles hide noise at the content-type level. But there's
no concept of "tangent" or "dead branch" in the UI. The phase timeline groups
related turns, but doesn't mark which phases were productive vs. exploratory.

**What's needed:**

```
Phase timeline with "signal" markers:

  ● EXPLORATION   Turns 0–1    "Initial concept discussion"
  ● EVALUATION    Turns 2–54   "Core implementation"        ★ signal
  ● EVALUATION    Turns 55–85  "Format pivot & debugging"   ★ signal
  ○ EXPLORATION   Turns 86–89  "Reflex tangent"             ← tangent
  ● EVALUATION    Turns 90–258 "Main development"           ★ signal
```

A "tangent" marker could be auto-detected when:
- A phase has low label-overlap with adjacent phases
- The user pivoted (Pivoting label) and then returned to the original topic
- The phase was marked as "infelicity" (Austin's term for a misfire)

**Design principle:** *Information hierarchy.* Not all content is equal.
Make the signal visually dominant; make the noise accessible but secondary.

---

### Goal 4: Extract Knowledge into a Permanent Home

> *"Promote good explanations, decisions, and reflections from chat scroll into
> notes that survive."*

**Current GUI:** ⚠️ Pipeline exists, but no viewer.

The extraction pipeline generates zettel files with YAML frontmatter. But
there's no UI to browse, search, or edit them. The user must open .md files
in a text editor or Obsidian.

**What's needed: A Knowledge Base view**

```
┌─────────────────────────────────────────────────────────────┐
│  📚 Knowledge Base                    31 notes · 2 projects │
├─────────────────────────────────────────────────────────────┤
│  Filter: [All] [Knowledge] [ADR] [Pattern]                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 📝 "Overview of Concepts in Your System Prompt"      │   │
│  │    git-llm · Turn 1 · Educational, Structuring      │   │
│  │    → related: Document Structure, Value Proposition  │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 📋 ADR: "JSONL as canonical format"                  │   │
│  │    git-llm · Turn 4 · Challenging, Pivoting         │   │
│  │    → related: Pi-native schema, Markdown fragility   │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🧠 "Architecture synthesis from user answers"        │   │
│  │    kuchnie · Turn 4 · Synthesizing                   │   │
│  │    → related: Walking skeleton, Domain model         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Design principle:** *The extracted notes ARE the product.* The session
viewer is the mine; the knowledge base is the vault. The vault should be
first-class, not a side effect.

---

### Goal 5: Compound Learning

> *"Build a personal web of notes where each new chat adds to and links into
> prior knowledge."*

**Current GUI:** ❌ Not served.

The backlink resolution works (42 links in the git-llm session). But there's
no UI to visualize or navigate the graph. The `related:` frontmatter sits in
YAML files.

**What's needed: A Graph view**

```
         ┌──────────────┐
         │  Clean Arch   │
         │  Concepts     │
         └──────┬───────┘
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐
│Doc     │ │SQLModel│ │Value   │
│Structure│ │Decision│ │Prop    │
└────┬───┘ └────┬───┘ └────────┘
     │          │
     ▼          ▼
┌────────┐ ┌────────┐
│Screaming│ │Reflex  │
│Reflex   │ │Framework│
└────────┘ └────────┘
```

Even a simple force-directed graph (D3.js, ~150 lines) would make the
knowledge web visible and navigable. Clicking a node opens the zettel.
Dragging rearranges. The graph grows with each new session.

**Design principle:** *Make connections visible.* A list of notes is a filing
cabinet. A graph of notes is a brain.

---

### Goal 6: Document Decisions Automatically

> *"Capture why a choice was made, not just the outcome."*

**Current GUI:** ⚠️ Extraction exists, no decision viewer.

The ADR trigger sequences detect decision patterns (Pivoting → Pragmatic →
Synthesizing). But the current GUI doesn't distinguish ADRs from knowledge
notes. A decision record should look different from a concept explanation.

**What's needed: ADR-specific card**

```
┌─────────────────────────────────────────────────────────────┐
│  📋 Architecture Decision Record                            │
├─────────────────────────────────────────────────────────────┤
│  Title: JSONL as canonical source format                    │
│  Status: Accepted                                           │
│  Date: 2026-06-28                                           │
│  Session: git-llm/019f0b65                                  │
│                                                             │
│  Context: User questioned markdown fragility.               │
│  Decision: Use JSONL as the canonical wire format.          │
│  Consequences: Markdown is still supported via conversion.  │
│                                                             │
│  Labels: Challenging → Analytical → Pragmatic               │
│                                                             │
│  [View source turns]  [View related ADRs]  [Edit]           │
└─────────────────────────────────────────────────────────────┘
```

**Design principle:** *Decisions are first-class artifacts.* They should have
their own view, their own schema, and their own navigation — not be buried
inside a generic note list.

---

## The Architecture Gap

The current GUI has **one view** (session viewer) that serves **one goal**
(navigate within a chat). The other five goals have no UI.

The missing piece is a **multi-view application** with a shared data layer:

```
                    ┌─────────────────┐
                    │  SQLite + FTS5   │
                    │  (single source) │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
  │  Dashboard   │    │   Session   │    │  Knowledge  │
  │  (Goal 1)   │    │   Viewer    │    │   Base      │
  │             │    │  (Goal 2,3) │    │ (Goal 4,5,6)│
  │ - Search    │    │             │    │             │
  │ - Filters   │    │ - Phases    │    │ - Notes     │
  │ - Recent    │    │ - Turns     │    │ - ADRs      │
  │ - Stats     │    │ - Labels    │    │ - Graph     │
  └─────────────┘    └─────────────┘    └─────────────┘
```

## Recommended Implementation Order

| Priority | View | Goals served | Effort |
|---|---|---|---|
| **1st** | Cross-session search (Dashboard) | Goal 1 | Small — FTS5 already works |
| **2nd** | Knowledge Base view | Goals 4, 6 | Medium — read from DB, render cards |
| **3rd** | Graph view | Goal 5 | Medium — D3 force graph from backlinks |
| **4th** | Session viewer improvements | Goals 2, 3 | Small — minimap, tangent markers |

**The single highest-impact feature is cross-session search.** It turns the
tool from "a viewer for one session" into "a search engine for your thinking
history." That's the moment the value proposition becomes real.
