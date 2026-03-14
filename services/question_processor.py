"""Question deduplication, validation, and normalization."""

from typing import Any

from services.constants import (
    ANSWER_KEY_MARKERS,
    ANSWER_LABEL_PATTERN,
    DOC_TIP_PATTERN,
    DUPLICATE_CONTENT_LITERALS,
    LEADING_NUMBER_PATTERN,
    OPTION_BULLET_PATTERN,
    OPTION_CHECKBOX_PATTERN,
    OPTION_LETTER_PATTERN,
    OPTION_NUMBER_PATTERN,
    QUESTION_TYPE_LABEL_PATTERN,
    STANDARD_ANNOTATION_PATTERN,
    UNDERSCORE_FILLER_PATTERN,
)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Normalize whitespace and case-fold text for comparison."""
    return " ".join(text.split()).casefold()


def _is_answer_key_text(text: str) -> bool:
    """Check if text appears to be an answer key header."""
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(marker in normalized for marker in ANSWER_KEY_MARKERS)


def _item_text_for_filter(item: dict[str, Any]) -> str:
    """Extract and normalize all text fields from an item for filtering."""
    parts = [
        str(item.get("text") or ""),
        str(item.get("title") or ""),
        str(item.get("table_text_preview") or ""),
    ]
    return _normalize_text(" ".join(part for part in parts if part))


def _strip_option_prefix(text: str) -> str:
    """Remove bullet, checkbox, number, and letter prefixes from text."""
    stripped = OPTION_BULLET_PATTERN.sub("", text)
    stripped = OPTION_CHECKBOX_PATTERN.sub("", stripped)
    stripped = OPTION_NUMBER_PATTERN.sub("", stripped)
    stripped = OPTION_LETTER_PATTERN.sub("", stripped)
    return stripped.strip()


def _is_duplicate_content(
    item: dict[str, Any],
    question_texts_set: set[str],
    option_texts_set: set[str],
) -> bool:
    """Check if a paragraph/section item duplicates question or option text."""
    if item["type"] not in {"paragraph", "section", "table", "image"}:
        return False
    text = _item_text_for_filter(item)
    if not text:
        return False
    if _is_answer_key_text(text):
        return True
    if UNDERSCORE_FILLER_PATTERN.match(text):
        return True
    if item.get("type") == "image" and item.get("source_kind") == "table":
        preview = _normalize_text(str(item.get("table_text_preview") or ""))
        if _is_answer_key_text(preview):
            return True
        return False
    text_no_num = LEADING_NUMBER_PATTERN.sub("", text).strip()
    texts_to_check = {text}
    if text_no_num and text_no_num != text:
        texts_to_check.add(text_no_num)
    for t in texts_to_check:
        if t in question_texts_set:
            return True
        for q_text in question_texts_set:
            if q_text and q_text in t:
                return True
            if t in q_text:
                return True
    if ANSWER_LABEL_PATTERN.match(text):
        return True
    for t in texts_to_check:
        if t in option_texts_set:
            return True
    stripped = _strip_option_prefix(text)
    if stripped and stripped in option_texts_set:
        return True
    if DOC_TIP_PATTERN.match(text) and (
        "google docs" in text or "google doc" in text
    ):
        return True
    if text in DUPLICATE_CONTENT_LITERALS:
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_questions(
    questions: list[dict[str, Any]],
    paragraph_items: list[tuple[int, str]],
    seen_questions: set[str],
) -> list[dict[str, Any]]:
    """Deduplicate, validate types, sort, and merge consecutive questions.

    Args:
        questions: Raw questions returned by the parser.
        paragraph_items: ``(doc_index, normalized_text)`` pairs for anchoring.
        seen_questions: Set of already-seen normalized question texts (mutated).

    Returns:
        Cleaned, sorted, and merged question list.
    """
    unique_questions = _deduplicate_and_validate(
        questions, paragraph_items, seen_questions
    )
    unique_questions.sort(key=lambda item: item.get("_question_index", 0))
    merged = _merge_consecutive(unique_questions)
    return merged


def build_dedup_sets(
    questions: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    """Build normalized question-text and option-text sets for filtering.

    Also pops the ``_dropped_preamble`` key from each question and adds it
    to the question texts set so duplicate paragraphs are filtered.

    Args:
        questions: The merged question list (modified in-place to pop preamble).

    Returns:
        A ``(question_texts_set, option_texts_set)`` tuple.
    """
    question_texts_set: set[str] = set()
    option_texts_set: set[str] = set()
    for q in questions:
        q_text = _normalize_text(str(q.get("question", "")))
        if q_text:
            question_texts_set.add(q_text)
        preamble = _normalize_text(str(q.pop("_dropped_preamble", "") or ""))
        if preamble:
            question_texts_set.add(preamble)
        for opt in q.get("options", []):
            opt_text = _normalize_text(str(opt))
            if opt_text:
                option_texts_set.add(opt_text)
    return question_texts_set, option_texts_set


def is_duplicate_content(
    item: dict[str, Any],
    question_texts_set: set[str],
    option_texts_set: set[str],
) -> bool:
    """Public wrapper for duplicate-content checking."""
    return _is_duplicate_content(item, question_texts_set, option_texts_set)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deduplicate_and_validate(
    questions: list[dict[str, Any]],
    paragraph_items: list[tuple[int, str]],
    seen_questions: set[str],
) -> list[dict[str, Any]]:
    """Remove duplicates, validate types, and anchor questions to doc index."""
    unique_questions: list[dict[str, Any]] = []
    for q in questions:
        question_text = str(q.get("question", "")).strip()
        # Strip leading question numbers (e.g. "28. Which..." → "Which...")
        question_text = LEADING_NUMBER_PATTERN.sub("", question_text).strip()
        # Strip standard annotation prefixes (e.g. "(RL.9-10.4) ...")
        question_text = STANDARD_ANNOTATION_PATTERN.sub("", question_text).strip()
        q["question"] = question_text

        if not question_text:
            continue
        # Skip question-type labels that aren't real questions
        if QUESTION_TYPE_LABEL_PATTERN.match(question_text):
            continue

        options = q.get("options") or []
        if not isinstance(options, list):
            options = []
        options = [str(opt).strip() for opt in options if str(opt).strip()]

        q_type = str(q.get("type", "multiple_choice")).strip().lower()
        allowed_types = {
            "multiple_choice",
            "checkbox",
            "short_answer",
            "paragraph",
        }
        if q_type not in allowed_types:
            q_type = "multiple_choice" if options else "short_answer"
        if q_type in {"multiple_choice", "checkbox"} and not options:
            q_type = "short_answer"

        q["type"] = q_type
        q["options"] = options

        normalized = " ".join(question_text.split()).casefold()
        if normalized in seen_questions:
            continue
        seen_questions.add(normalized)

        question_index = _find_question_anchor(normalized, paragraph_items)
        q["_question_index"] = question_index

        unique_questions.append(q)
    return unique_questions


def _find_question_anchor(
    normalized: str, paragraph_items: list[tuple[int, str]]
) -> int:
    """Find the best document index for a question text."""
    for idx, item_text in paragraph_items:
        if normalized and normalized in item_text:
            return idx
        if item_text and item_text in normalized:
            return idx
    return 0


def _merge_consecutive(
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge consecutive questions that share identical option sets."""
    merged_questions: list[dict[str, Any]] = []
    skip_next = False
    for idx in range(len(questions)):
        if skip_next:
            skip_next = False
            continue
        q = questions[idx]
        if idx + 1 < len(questions):
            next_q = questions[idx + 1]
            q_opts = [
                _normalize_text(str(o))
                for o in q.get("options", [])
                if str(o).strip()
            ]
            next_opts = [
                _normalize_text(str(o))
                for o in next_q.get("options", [])
                if str(o).strip()
            ]
            if q_opts and q_opts == next_opts:
                q_text = str(q.get("question", ""))
                next_text = str(next_q.get("question", ""))
                if "?" in next_text:
                    keep, drop = next_q, q
                elif "?" in q_text:
                    keep, drop = q, next_q
                else:
                    keep, drop = next_q, q
                keep["_question_index"] = min(
                    int(q.get("_question_index", 0)),
                    int(next_q.get("_question_index", 0)),
                )
                keep["_dropped_preamble"] = str(drop.get("question", ""))
                merged_questions.append(keep)
                skip_next = True
                continue
        merged_questions.append(q)
    return merged_questions
