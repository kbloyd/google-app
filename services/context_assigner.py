"""Anchor-based context assignment for questions."""

import logging
import os
from typing import Any

from services.question_processor import is_duplicate_content

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assign_context(
    questions: list[dict[str, Any]],
    doc_items: list[dict[str, Any]],
    eligible_item_ids: set[int],
    item_by_id: dict[int, dict[str, Any]],
    item_id_to_index: dict[int, int],
    item_ids_in_order: list[int],
    question_texts_set: set[str],
    option_texts_set: set[str],
) -> None:
    """Assign context item IDs to each question in-place.

    For every eligible document item that is not duplicate content, the
    algorithm finds the best owning question (preferring items that appear
    *before* the question anchor, in the same section, closest distance,
    and highest type priority).

    After initial assignment, consecutive paragraph context items are
    consolidated into a single merged item.

    Args:
        questions: Question dicts (modified in-place; ``context_ids`` is set).
        doc_items: Full document items list (may be appended to during merging).
        eligible_item_ids: Item IDs that precede the answer-key boundary.
        item_by_id: Mapping of item ID → item dict (may grow during merging).
        item_id_to_index: Mapping of item ID → positional index.
        item_ids_in_order: All item IDs in document order.
        question_texts_set: Normalized question texts for duplicate filtering.
        option_texts_set: Normalized option texts for duplicate filtering.
    """
    section_starts = _build_section_starts(item_ids_in_order, item_by_id, item_id_to_index)

    context_item_ids = [
        item_id
        for item_id in item_ids_in_order
        if item_id in eligible_item_ids
        and item_by_id[item_id]["type"]
        in {"section", "paragraph", "image", "table"}
        and not is_duplicate_content(
            item_by_id[item_id], question_texts_set, option_texts_set
        )
    ]

    q_anchors = [
        (idx, int(q.get("_question_index", 0))) for idx, q in enumerate(questions)
    ]

    claim_map = _build_claim_map(
        context_item_ids,
        q_anchors,
        item_id_to_index,
        item_ids_in_order,
        item_by_id,
        section_starts,
    )

    for idx, q in enumerate(questions):
        assigned = sorted(
            [
                ctx_id
                for ctx_id, owner_idx in claim_map.items()
                if owner_idx == idx
            ],
            key=lambda cid: item_id_to_index.get(cid, 0),
        )
        q["context_ids"] = assigned

    _consolidate_paragraphs(questions, doc_items, item_by_id, item_ids_in_order)

    _debug_trace(questions, item_by_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_section_starts(
    item_ids_in_order: list[int],
    item_by_id: dict[int, dict[str, Any]],
    item_id_to_index: dict[int, int],
) -> list[int]:
    """Return a sorted list of section start indices."""
    section_starts: list[int] = [0]
    for item_id in item_ids_in_order:
        item = item_by_id[item_id]
        if item.get("type") == "section":
            section_starts.append(item_id_to_index[item_id])
    return section_starts


def _section_of(doc_index: int, section_starts: list[int]) -> int:
    """Return the section number an index belongs to."""
    sec = 0
    for s_idx, start in enumerate(section_starts):
        if doc_index >= start:
            sec = s_idx
    return sec


def _score_candidate(
    ctx_index: int,
    q_index: int,
    q_section: int,
    item_by_id: dict[int, dict[str, Any]],
    item_ids_in_order: list[int],
    section_starts: list[int],
) -> tuple[int, int, int]:
    """Return ``(section_match, -distance, type_priority)``."""
    ctx_section = _section_of(ctx_index, section_starts)
    section_match = 1 if ctx_section == q_section else 0
    distance = abs(q_index - ctx_index)
    item = item_by_id[item_ids_in_order[ctx_index]]
    type_priority = (
        3
        if item["type"] == "image"
        else 2
        if item["type"] == "table"
        else 1
        if item["type"] == "section"
        else 0
    )
    return (section_match, -distance, type_priority)


def _build_claim_map(
    context_item_ids: list[int],
    q_anchors: list[tuple[int, int]],
    item_id_to_index: dict[int, int],
    item_ids_in_order: list[int],
    item_by_id: dict[int, dict[str, Any]],
    section_starts: list[int],
) -> dict[int, int]:
    """Map each context item ID to its owning question list index."""
    claim_map: dict[int, int] = {}
    for ctx_id in context_item_ids:
        ctx_index = item_id_to_index[ctx_id]
        best_q_idx: int | None = None
        best_score: tuple[int, int, int] | None = None
        for q_idx, q_anchor in q_anchors:
            if ctx_index >= q_anchor:
                continue
            score = _score_candidate(
                ctx_index,
                q_anchor,
                _section_of(q_anchor, section_starts),
                item_by_id,
                item_ids_in_order,
                section_starts,
            )
            if best_score is None or score > best_score:
                best_score = score
                best_q_idx = q_idx
        if best_q_idx is None:
            for q_idx, q_anchor in reversed(q_anchors):
                if q_anchor <= ctx_index:
                    best_q_idx = q_idx
                    break
        if best_q_idx is not None:
            claim_map[ctx_id] = best_q_idx
    return claim_map


def _consolidate_paragraphs(
    questions: list[dict[str, Any]],
    doc_items: list[dict[str, Any]],
    item_by_id: dict[int, dict[str, Any]],
    item_ids_in_order: list[int],
) -> None:
    """Merge runs of adjacent paragraph context items into a single item."""
    next_synthetic_id = max(item_ids_in_order) + 1 if item_ids_in_order else 1

    for q in questions:
        ctx_ids = q.get("context_ids", [])
        if len(ctx_ids) <= 1:
            continue

        new_ctx_ids: list[int] = []
        paragraph_run: list[int] = []

        def _flush(
            run: list[int],
            out: list[int],
            synth_id: int,
        ) -> int:
            if len(run) <= 1:
                out.extend(run)
                return synth_id
            merged_text = "\n".join(
                str(item_by_id[pid].get("text") or "") for pid in run
            )
            merged_item: dict[str, Any] = {
                "id": synth_id,
                "type": "paragraph",
                "text": merged_text,
            }
            doc_items.append(merged_item)
            item_by_id[synth_id] = merged_item
            out.append(synth_id)
            return synth_id + 1

        for cid in ctx_ids:
            item = item_by_id[cid]
            if item["type"] == "paragraph":
                paragraph_run.append(cid)
            else:
                next_synthetic_id = _flush(
                    paragraph_run, new_ctx_ids, next_synthetic_id
                )
                paragraph_run = []
                new_ctx_ids.append(cid)
        next_synthetic_id = _flush(
            paragraph_run, new_ctx_ids, next_synthetic_id
        )
        q["context_ids"] = new_ctx_ids


def _debug_trace(
    questions: list[dict[str, Any]],
    item_by_id: dict[int, dict[str, Any]],
) -> None:
    """Log context assignment details when DEBUG_CONTEXT is set."""
    if not os.getenv("DEBUG_CONTEXT"):
        return
    for idx, q in enumerate(questions):
        q_text = str(q.get("question", ""))[:60]
        ctx_ids = q.get("context_ids", [])
        ctx_details = []
        for cid in ctx_ids:
            ci = item_by_id.get(cid, {})
            ctx_details.append(
                f"  id={cid} type={ci.get('type')} "
                f"source_kind={ci.get('source_kind', '-')} "
                f"title={str(ci.get('title') or ci.get('text') or '')[:40]}"
            )
        logger.info(
            "Q%d [anchor=%s]: %s\n  context_ids=%s\n%s",
            idx,
            q.get("_question_index", "?"),
            q_text,
            ctx_ids,
            "\n".join(ctx_details) if ctx_details else "  (none)",
        )
