"""Answer key extraction from tables and paragraphs."""

import re
from typing import Any

from services.constants import AK_PARAGRAPH_PATTERN, INLINE_ANSWER_PATTERN


def parse_answer_key(
    item_ids_in_order: list[int],
    item_by_id: dict[int, dict[str, Any]],
    item_id_to_index: dict[int, int],
    answer_key_start_index: int,
) -> dict[int, dict[str, str]]:
    """Extract an answer key by merging inline, table, and paragraph sources.

    Priority (later sources override earlier ones):
    1. Inline answers found before the answer-key section (lowest).
    2. Table-based answers from the answer-key section.
    3. Paragraph-based answers from the answer-key section (highest).

    Args:
        item_ids_in_order: Document item IDs in document order.
        item_by_id: Mapping of item ID → item dict.
        item_id_to_index: Mapping of item ID → positional index.
        answer_key_start_index: Index at which the answer-key section begins.

    Returns:
        Mapping of 1-based question number → ``{"correct_answer": …, "explanation": …}``.
    """
    answer_key: dict[int, dict[str, str]] = {}

    # Inline answers (lowest priority)
    inline = _parse_inline_answer_key(
        item_ids_in_order, item_by_id, item_id_to_index, answer_key_start_index
    )
    answer_key.update(inline)

    # Table-based answers (override inline)
    table = _parse_table_answer_key(
        item_ids_in_order, item_by_id, item_id_to_index, answer_key_start_index
    )
    answer_key.update(table)

    # Paragraph-based answers (highest priority)
    paragraph = _parse_paragraph_answer_key(
        item_ids_in_order, item_by_id, item_id_to_index, answer_key_start_index
    )
    answer_key.update(paragraph)

    return answer_key


def _parse_inline_answer_key(
    item_ids_in_order: list[int],
    item_by_id: dict[int, dict[str, Any]],
    item_id_to_index: dict[int, int],
    answer_key_start_index: int,
) -> dict[int, dict[str, str]]:
    """Extract inline answer keys from paragraphs before the answer-key section."""
    answer_key: dict[int, dict[str, str]] = {}
    question_counter = 0
    question_number_pattern = re.compile(r"^\d+[.)]\s+")

    for item_id in item_ids_in_order:
        if item_id_to_index[item_id] >= answer_key_start_index:
            break

        item = item_by_id[item_id]
        if item.get("type") not in {"paragraph", "section"}:
            continue

        text = str(item.get("text") or item.get("title") or "").strip()
        if not text:
            continue

        # Check if this looks like a new question
        if question_number_pattern.match(text):
            question_counter += 1

        # Check for inline answer
        match = INLINE_ANSWER_PATTERN.search(text)
        if match and question_counter > 0:
            answer_text = match.group(1).strip()
            answer_key[question_counter] = {
                "correct_answer": answer_text,
                "explanation": "",
            }

    return answer_key


def _parse_table_answer_key(
    item_ids_in_order: list[int],
    item_by_id: dict[int, dict[str, Any]],
    item_id_to_index: dict[int, int],
    answer_key_start_index: int,
) -> dict[int, dict[str, str]]:
    """Extract answer key entries from table rows."""
    answer_key: dict[int, dict[str, str]] = {}

    for item_id in item_ids_in_order:
        if item_id_to_index[item_id] < answer_key_start_index:
            continue
        item = item_by_id[item_id]
        rows = item.get("table_rows")
        if not rows or len(rows) < 2:
            continue

        header = [cell.strip().casefold() for cell in rows[0]]
        q_col = ans_col = exp_col = None
        for ci, h in enumerate(header):
            if "question" in h:
                q_col = ci
            elif "correct" in h or "answer" in h:
                if ans_col is None:
                    ans_col = ci
            elif "explanation" in h or "feedback" in h:
                exp_col = ci
        if q_col is None:
            q_col = 0
        if ans_col is None:
            ans_col = 1 if len(header) > 1 else 0
        if exp_col is None and len(header) > 2:
            exp_col = 2

        for data_row in rows[1:]:
            if len(data_row) <= max(q_col, ans_col):
                continue
            raw_q = data_row[q_col].strip()
            q_num_match = re.match(r"(\d+)", raw_q)
            if not q_num_match:
                continue
            q_num = int(q_num_match.group(1))
            correct_ans = (
                data_row[ans_col].strip() if ans_col < len(data_row) else ""
            )
            explanation = ""
            if exp_col is not None and exp_col < len(data_row):
                explanation = data_row[exp_col].strip()
            if correct_ans:
                answer_key[q_num] = {
                    "correct_answer": correct_ans,
                    "explanation": explanation,
                }

    return answer_key


def _parse_paragraph_answer_key(
    item_ids_in_order: list[int],
    item_by_id: dict[int, dict[str, Any]],
    item_id_to_index: dict[int, int],
    answer_key_start_index: int,
) -> dict[int, dict[str, str]]:
    """Extract answer key entries from paragraph text (e.g. ``1. B) 1985``)."""
    answer_key: dict[int, dict[str, str]] = {}

    ak_text_parts: list[str] = []
    for item_id in item_ids_in_order:
        if item_id_to_index[item_id] < answer_key_start_index:
            continue
        item = item_by_id[item_id]
        raw = str(item.get("text") or item.get("title") or "").strip()
        if raw:
            ak_text_parts.append(raw)

    ak_full_text = " ".join(ak_text_parts)
    for m in AK_PARAGRAPH_PATTERN.finditer(ak_full_text):
        q_num = int(m.group(1))
        letter = m.group(2).upper()
        ans_text = m.group(3).strip()
        explanation = ""
        paren_match = re.search(r"\((.+?)\)\s*$", ans_text)
        if paren_match:
            explanation = paren_match.group(1).strip()
            ans_text = ans_text[: paren_match.start()].strip()
        answer_key[q_num] = {
            "correct_answer": f"{letter}) {ans_text}" if ans_text else letter,
            "explanation": explanation,
        }

    return answer_key
