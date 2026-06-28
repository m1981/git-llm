"""
Dialogue-act taxonomy.

The user's 20-label dictionary, grouped under Austin's 5 master classes.
We keep both axes explicit so the LLM-labeler and the extractor can reason
on either granularity. A MIDAS-hint column is provided for future migration
to a research-grade taxonomy.

References:
    - Austin, "How to Do Things with Words" (1962)
    - Switchboard DAMSL (SwDA): https://web.stanford.edu/~jurafsky/ws97/manual.august1.html
    - MIDAS (Yu & Yu, 2019): https://arxiv.org/abs/1908.10023
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MasterClass(StrEnum):
    """Austin's five illocutionary classes (renamed for engineering clarity)."""

    EXPOSITIVE = "Expositive"      # Informational: explain, define, clarify
    EXERCITIVE = "Exercitive"      # Directive: order, instruct, pivot
    VERDICTIVE = "Verdictive"      # Analytical: judge, assess, correct
    COMMISSIVE = "Commissive"      # Generative: promise, plan, structure
    BEHABITIVE = "Behabitive"      # Evaluative: react, challenge, validate


@dataclass(frozen=True, slots=True)
class LabelSpec:
    name: str
    role: Role
    master_class: MasterClass
    midas_hint: str  # rough mapping to MIDAS taxonomy for future migration
    description: str


# fmt: off
LABELS: tuple[LabelSpec, ...] = (
    # ---- User labels (10) ----
    LabelSpec("Inquiring",         Role.USER, MasterClass.EXPOSITIVE, "open_question_factual",  "Asking for information."),
    LabelSpec("Scenario-Setting",  Role.USER, MasterClass.EXPOSITIVE, "statement",              "Providing context, mockups, or background."),
    LabelSpec("Providing-Context", Role.USER, MasterClass.EXPOSITIVE, "statement",              "Sharing code dumps, logs, or specifications."),
    LabelSpec("Clarifying",        Role.USER, MasterClass.EXPOSITIVE, "open_question_factual",  "Asking for definitions or disambiguation."),
    LabelSpec("Deep-Diving",       Role.USER, MasterClass.EXPOSITIVE, "open_question_opinion",  "Requesting details on a specific point."),
    LabelSpec("Directing",         Role.USER, MasterClass.EXERCITIVE, "command",                "Giving specific, actionable instructions."),
    LabelSpec("Pivoting",          Role.USER, MasterClass.EXERCITIVE, "command",                "Changing tech stack, scope, or direction."),
    LabelSpec("Seeking-Validation",Role.USER, MasterClass.BEHABITIVE, "open_question_opinion",  "Asking for review or approval."),
    LabelSpec("Challenging",       Role.USER, MasterClass.BEHABITIVE, "neg_answer",             "Debating, pushing back, questioning a claim."),
    LabelSpec("Reflective",        Role.USER, MasterClass.BEHABITIVE, "comment",                "Looking back at previous choices or reasoning."),

    # ---- Assistant labels (10) ----
    LabelSpec("Educational",       Role.ASSISTANT, MasterClass.EXPOSITIVE, "statement",         "Explaining a concept from first principles."),
    LabelSpec("Analytical",        Role.ASSISTANT, MasterClass.VERDICTIVE, "statement",         "Breaking down code, mockups, or arguments."),
    LabelSpec("Prescriptive",      Role.ASSISTANT, MasterClass.EXERCITIVE, "command",           "Telling the user exactly what to do."),
    LabelSpec("Correcting",        Role.ASSISTANT, MasterClass.VERDICTIVE, "neg_answer",        "Fixing flaws, errors, or misconceptions."),
    LabelSpec("Validating",        Role.ASSISTANT, MasterClass.BEHABITIVE, "pos_answer",        "Praising good choices."),
    LabelSpec("Pragmatic",         Role.ASSISTANT, MasterClass.VERDICTIVE, "opinion",           "Suggesting real-world compromises and trade-offs."),
    LabelSpec("Visualizing",       Role.ASSISTANT, MasterClass.COMMISSIVE, "statement",         "Producing diagrams, tables, or visual structures."),
    LabelSpec("Structuring",       Role.ASSISTANT, MasterClass.COMMISSIVE, "statement",         "Organizing files, prompts, or specs."),
    LabelSpec("Warning",           Role.ASSISTANT, MasterClass.VERDICTIVE, "opinion",           "Pointing out risks or anti-patterns."),
    LabelSpec("Synthesizing",      Role.ASSISTANT, MasterClass.COMMISSIVE, "statement",         "Bringing multiple concepts into a unified artifact."),
)
# fmt: on

LABEL_NAMES: frozenset[str] = frozenset(spec.name for spec in LABELS)
USER_LABELS: tuple[str, ...] = tuple(s.name for s in LABELS if s.role == Role.USER)
ASSISTANT_LABELS: tuple[str, ...] = tuple(s.name for s in LABELS if s.role == Role.ASSISTANT)
BY_NAME: dict[str, LabelSpec] = {s.name: s for s in LABELS}


# ---- Extraction triggers ----------------------------------------------------
# Rules that fire when a turn (or a window of turns) should become an artifact
# in the Zettelkasten. The (kind, labels) tuples mean: any turn carrying *any*
# of the listed labels qualifies. Sequences (tuples of tuples) mean ordered
# adjacency over consecutive turns.

KNOWLEDGE_TRIGGERS: tuple[tuple[str, ...], ...] = (
    ("Educational",),
    ("Reflective",),
    ("Synthesizing",),            # multi-concept integration — high signal
    ("Pragmatic", "Warning"),     # trade-off reasoning with risk awareness
)

ADR_TRIGGER_SEQUENCES: tuple[tuple[tuple[str, ...], ...], ...] = (
    # (Pivot or Challenge) → Pragmatic/Analytical → Synthesizing/Structuring
    (("Pivoting", "Challenging"), ("Pragmatic", "Analytical"), ("Synthesizing", "Structuring")),
)
