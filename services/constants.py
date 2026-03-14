"""Shared regex patterns and constants for document-to-form conversion."""

import re

# --- Compiled regex patterns ---
ANSWER_LABEL_PATTERN = re.compile(r"^[a-d]\)\s+", re.IGNORECASE)
BULLET_CHECKBOX_PATTERN = re.compile(
    r"^[●•\-\*\d.)\s]*\[[\sx]?\]\s*", re.IGNORECASE
)
NUMBERED_OPTION_PATTERN = re.compile(r"^\d+[.)]\s+")
DOC_TIP_PATTERN = re.compile(r"^tip\s*:", re.IGNORECASE)
LEADING_NUMBER_PATTERN = re.compile(r"^\d+[.)]\s*")
UNDERSCORE_FILLER_PATTERN = re.compile(r"^[_\s]+$")
AK_PARAGRAPH_PATTERN = re.compile(
    r"(\d+)\.\s*([A-Da-d])\)\s*(.+?)(?=\s*\d+\.\s*[A-Da-d]\)|$)",
    re.DOTALL,
)
ANSWER_NORMALIZE_PATTERN = re.compile(r"^[A-Da-d0-9]+[.)]\s*")
OPTION_BULLET_PATTERN = re.compile(r"^[●•\-\*]\s*")
OPTION_CHECKBOX_PATTERN = re.compile(r"^\[[\sx]?\]\s*")
OPTION_NUMBER_PATTERN = re.compile(r"^\d+[.)]\s+")
OPTION_LETTER_PATTERN = re.compile(r"^[a-d]\)\s+", re.IGNORECASE)
STANDARD_ANNOTATION_PATTERN = re.compile(r"^\([A-Z]+[\.\d\-]+\)\s*")
QUESTION_TYPE_LABEL_PATTERN = re.compile(
    r"^(?:Multiple Choice|Short Response|Extended Response|Fill in the Blank|Works Cited Construction)"
    r"(?:\s*[–\-]\s*.+?)?\s*$",
    re.IGNORECASE,
)
INLINE_ANSWER_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:answer|correct answer|ans)\s*(?:\((?:sample response|sample)\))?\s*[:\-]\s*(.+)",
    re.IGNORECASE,
)

# --- Frozen sets for quick membership tests ---
ANSWER_KEY_MARKERS: frozenset[str] = frozenset(
    {
        "answer key",
        "correct answer",
        "correct answers",
        "explanation",
        "solutions",
        "solution key",
    }
)

DUPLICATE_CONTENT_LITERALS: frozenset[str] = frozenset(
    {
        "mark only one oval",
        "mark only one oval.",
        "check all that apply",
        "check all that apply.",
    }
)
