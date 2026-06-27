# Value Proposition & User Goals

> *"My conversations with AI are some of the most valuable thinking I do all week.
> And almost all of it disappears."*

---

## 1. The One-Paragraph Pitch

When you talk to an AI assistant for hours about a real problem, you produce
two things at once: **progress on the problem** and **knowledge worth keeping**.
Today, both are dumped into the same chronological scroll and forgotten within
days. **This project turns that scroll into a structured, searchable, growing
personal brain** — where every chat deposits durable notes, decisions, and
lessons that future-you can actually find and reuse.

---

## 2. The Problem (Why This Exists)

Anyone who uses LLMs heavily for thinking work hits the same wall:

| Symptom | What it really costs you |
|---|---|
| "I know we figured this out two weeks ago — but where?" | Hours of re-reading old chats, or worse, re-solving the same problem |
| 40-turn conversations that are 80% noise | Cognitive fatigue; you stop opening old chats at all |
| Brilliant explanations buried inside a debugging session | Knowledge dies the moment the chat scrolls off-screen |
| Decisions made, then quietly reversed three turns later | You can't trust your own history |
| Each new chat starts from zero | No compounding — you pay full price for context every time |

The chat interface is excellent for **thinking in the moment** and terrible for
**remembering across time**. It is the lab notebook of the AI era — except the
pages are written in disappearing ink.

---

## 3. The Value Proposition

> **Treat every AI conversation as a deposit into a personal knowledge bank,
> not a disposable transcript.**

| Before | After |
|---|---|
| Chats are a wall of text | Chats are a map of labeled moves |
| Knowledge is trapped in scrollback | Knowledge is extracted into linked notes |
| Decisions are buried in tangents | Decisions are recorded as standalone receipts |
| You search by remembering keywords | You search by intent ("show me every *warning* about databases") |
| Each chat is an island | Chats link to each other through shared concepts |
| Effort evaporates | Effort compounds |

The system pays you back **the second time** you need something you already
figured out — and every time after that, forever.

---

## 4. User Goals (Jobs-To-Be-Done)

### Functional goals — what the user needs to *do*

1. **Recall across chats.** Find a specific insight without remembering which
   conversation it was in.
2. **Navigate within a chat.** Skim a 40-turn discussion in 60 seconds and jump
   to the part that matters.
3. **Separate signal from noise.** Hide tangents, dead ends, and abandoned
   branches without deleting them.
4. **Extract knowledge into a permanent home.** Promote good explanations,
   decisions, and reflections from chat scroll into notes that survive.
5. **Compound learning.** Build a personal web of notes where each new chat
   adds to and links into prior knowledge.
6. **Document decisions automatically.** Capture *why* a choice was made, not
   just the outcome — so future-you (or your team) doesn't re-litigate it.

### Emotional goals — what the user needs to *feel*

- **Calm.** Trust that nothing important is being lost.
- **Ownership.** The output of AI collaboration feels like *your* asset, not
  rented thinking.
- **Momentum.** Each session builds on the last, instead of resetting.

### Social goals — what the user needs to *share*

- Show teammates the reasoning behind a decision, not just the verdict.
- Teach others from real, traceable artifacts.
- Demonstrate thinking quality, not just output volume.

---

## 5. The Theory Toolkit — Explained for a Non-Technical Reader

The project leans on five ideas with intimidating names. Each one solves a
specific link in the chain. Here is what each one actually *does*, in plain
language.

### 🎭 Austin's Speech Act Theory — "What is this sentence *doing*?"

**The intimidating version:** A 1960s philosophy framework that classifies
utterances by their illocutionary force.

**The plain version:** Think of reading a play. When a character says *"I'll
be there at noon,"* the words aren't just information — they're an **action**
(a promise). Austin gave us a vocabulary for the actions hiding inside
sentences: *asking, instructing, evaluating, promising, deciding.*

**Why we need it here:** To organize a chat, we can't just ask *"what is this
turn about?"* (databases? UI?). We need to ask *"what is this turn DOING?"*
Because the action tells us what to do with it later:

- A turn that **decides** something → goes into a Decision Record.
- A turn that **explains** a concept → goes into a Knowledge Note.
- A turn that **abandons** a direction → gets quarantined as a dead branch.
- A turn that just **clarifies** → can usually be ignored.

Without Austin's lens, every turn looks equally important. With it, the chat
sorts itself.

### 📚 Dialogue Act Modeling, SwDA, and MIDAS — "Standardized action names"

**The intimidating version:** SwDA (Switchboard Dialog Act Corpus) is a
research dataset of 220,000 phone-call sentences tagged with 42 dialogue-act
labels. MIDAS is a modern equivalent designed for human-to-AI chat.

**The plain version:** Think of air-traffic-control radio language. Pilots
worldwide say *"Roger,"* *"Wilco,"* *"Mayday"* — never *"okay buddy"* —
because standardized vocabulary prevents disasters. Linguists and AI
researchers have spent decades building a similar standardized vocabulary
for conversation moves. SwDA is the classic version; MIDAS is the modern
one built for chatbot conversations.

**Why we need it here:** You could invent your own 20 labels (and you did —
they're good). But there is enormous value in piggy-backing on a standard:

- **Free automation.** Software already exists that can read a sentence and
  output *"this is a question,"* *"this is a confirmation,"* *"this is an
  opinion."* If we map your labels to MIDAS, that software can label your
  chats *for you* — you don't have to do it by hand.
- **Future-proofing.** When better tools come along, they'll speak MIDAS.
  You won't be stuck with a private vocabulary nobody else understands.
- **Reliability.** Industry-tested categories have fewer edge cases than
  hand-rolled ones.

In short: SwDA and MIDAS turn your idea from *"a personal labeling habit"*
into *"a pipeline a computer can run."*

### 🗂️ Zettelkasten — "A second brain that grows links"

**The intimidating version:** A note-taking method invented by sociologist
Niklas Luhmann, who used it to write 70+ books from 90,000 interlinked
index cards.

**The plain version:** Think of Wikipedia, but for one person. Every fact
gets its own tiny article. Every article links to related articles. Over
years, you build a personal Wikipedia of everything you've ever learned —
and the links between articles often teach you things you didn't realize
you knew.

**Why we need it here:** Extracted knowledge has to *live somewhere good*.
A folder full of disconnected text files is a graveyard. Zettelkasten gives
us the destination:

- Each extracted insight becomes a tiny, self-contained note.
- Notes link to other notes by concept.
- The web grows organically — not by hierarchy.
- Three weeks later, when you ask *"what did I learn about connection
  pooling?"*, you don't just see one answer — you see the answer **plus
  every related note you've ever written**.

This is the engine of **compounding**. Without it, extracted notes pile up
dead. With it, every new note makes the old ones more valuable.

### 🤖 Natural Language Processing (NLP) — "Software that reads text"

**The intimidating version:** The computational discipline for processing
human language.

**The plain version:** Think of spell-check, but for meaning instead of
typos. NLP tools can scan thousands of pages and answer questions like
*"which sentences are questions?"* or *"which paragraphs are about
databases?"* without a human reading them.

**Why we need it here:** NLP is the **automation muscle**. It's how a
computer applies Austin's lens and MIDAS labels to your chats at scale.
Without NLP, you'd have to read and tag every turn yourself — which means
the system would never get used. With NLP, the labeling happens silently
in the background.

### 📜 Architecture Decision Records (ADRs) — "Decision receipts"

**The intimidating version:** A software-engineering convention for
recording architectural choices.

**The plain version:** Think of a court ruling. It captures:
- What was decided
- What options were considered
- Why this option won
- What the consequences are

Months later, you remember the *reasoning*, not just the outcome.

**Why we need it here:** Many of your AI conversations end with a real
decision (*"let's use SQLModel instead of separate domain models"*). If we
just save the answer, future-you won't remember why. If we save it as an
ADR, you can re-read the rationale and either trust it or revisit it. This
is one of the artifact types the system automatically extracts when it
detects a *decision* speech-act pattern.

---

## 6. How the Theories Connect (The Value Chain)

Each theory is one link in a chain. Skip a link, and the chain breaks.

```
   ┌──────────────────────────────────────────────────────────────┐
   │  RAW CHAT                                                     │
   │  40 turns of mixed signal + noise                             │
   └────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼   "What is each turn DOING?"
   ┌──────────────────────────────────────────────────────────────┐
   │  AUSTIN'S LENS                                                │
   │  Every turn gets classified by its action                     │
   └────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼   "Use names that machines understand"
   ┌──────────────────────────────────────────────────────────────┐
   │  MIDAS / SwDA VOCABULARY                                      │
   │  Standardized labels, ready for automation                    │
   └────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼   "Let software do the tagging"
   ┌──────────────────────────────────────────────────────────────┐
   │  NLP PIPELINE                                                 │
   │  Labels applied automatically to every turn                   │
   └────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼   "Promote the gold, hide the noise"
   ┌──────────────────────────────────────────────────────────────┐
   │  EXTRACTION                                                   │
   │  Decisions → ADRs.  Explanations → Knowledge notes.           │
   │  Dead ends → quarantined.                                     │
   └────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼   "Give the notes a home that grows"
   ┌──────────────────────────────────────────────────────────────┐
   │  ZETTELKASTEN                                                 │
   │  Linked, atomic notes that compound over time                 │
   └────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  YOUR PERSONAL BRAIN                                          │
   │  Searchable. Reusable. Shareable. Permanent.                  │
   └──────────────────────────────────────────────────────────────┘
```

### What each link costs if you skip it

- **No Austin** → You can't decide what each turn *is*, so you can't route it.
- **No MIDAS / SwDA** → You invent private labels nobody else can automate.
- **No NLP** → You must label by hand. The system dies of friction.
- **No ADRs** → Decisions get re-litigated. You distrust your own history.
- **No Zettelkasten** → Extracted notes pile up disconnected. No compounding.

---

## 7. What This Means In Plain English

Imagine this scenario, one year from today:

> You're starting a new project. You vaguely remember discussing
> "connection pooling" with an AI months ago, in some chat about a
> different project. You type three words into your personal brain.
>
> Up comes:
> - The original turn where the issue was diagnosed.
> - The decision record explaining why you chose one fix over another.
> - Two related notes on async patterns you wrote later.
> - A warning note from another chat where the same pattern bit you again.
>
> You read for 90 seconds and move on. You just saved three hours and
> avoided repeating a mistake.

**That moment** is the value proposition. Everything in this project —
Austin, MIDAS, NLP, Zettelkasten, ADRs — exists to make that moment
possible, automatically, for every conversation you have from now on.

---

## 8. Non-Goals (What This Is NOT)

To keep the project honest:

- ❌ Not a chat client. We don't replace ChatGPT/Claude — we ingest their
  exports.
- ❌ Not a perfect taxonomy. Labels are a means, not the product.
- ❌ Not a team wiki. This is a *personal* knowledge bank first.
- ❌ Not real-time. Extraction runs after chats end, not during.
- ❌ Not a replacement for thinking. It captures thinking; it doesn't do it.

---

## 9. Success Looks Like

You will know the system works when:

1. You stop fearing the end of a long chat — because nothing valuable will
   be lost.
2. You start *quoting your own past notes* in new chats, instead of
   re-explaining context.
3. You can answer *"have I thought about this before?"* in under a minute.
4. Your decision rationale survives the original decision by years.
5. Your AI conversations feel like investments, not consumption.
