import json
import logging
import os
import time
from typing import Any

from anthropic import Anthropic, APIStatusError, RateLimitError

logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20250929")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))


SYSTEM_PROMPT = """You are a helpful assistant that extracts multiple choice quiz questions from text.

Given a Google Doc containing quiz questions, extract all questions and convert them to a structured format.

Return a JSON array with objects containing:
- "question": The question text
- "type": "multiple_choice", "checkbox", "short_answer", or "paragraph"
- "options": Array of answer choices (2-4 options typical)
- "required": boolean (default: false)
- "context_ids": Optional array of numeric ids for nearby context items

Example output format:
[
  {
    "question": "What is the capital of France?",
    "type": "multiple_choice",
    "options": ["London", "Paris", "Berlin", "Madrid"],
    "required": true
  },
  {
    "question": "Which of the following are programming languages?",
    "type": "checkbox",
    "options": ["Python", "HTML", "JavaScript", "CSS"],
    "required": false
    },
    {
        "question": "Briefly explain the difference between HTTP and HTTPS.",
        "type": "short_answer",
        "required": false
  }
]

The document may include tables, images, drawings, charts, or other non-text items.
Ignore those non-question elements and focus on question text.

Use context_ids to reference any non-question items (tables, images, paragraphs)
that should appear immediately before the question in the final form. Each
question should appear exactly once. Do not split a single question into
multiple question entries.

Type rules:
- Use "multiple_choice" when exactly one option should be selected.
- Use "checkbox" when multiple options may be selected.
- Use "short_answer" for brief free-text responses.
- Use "paragraph" for longer free-text responses (essay/explanation prompts).

Ignore any answer key, solution key, or explanation section intended for graders.
Do not extract answer-key content as questions or context.

Extract ALL questions from the document. Only output valid JSON, no explanation."""


_client: Anthropic | None = None


def _get_client() -> Anthropic:
    """Return a lazily-cached Anthropic client."""
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        _client = Anthropic(api_key=api_key)
    return _client


def _parse_json_response(content: str) -> list[dict[str, Any]]:
    """Strip markdown fences and parse JSON from LLM response."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        questions = json.loads(content)
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse AI response as JSON: {content}") from e

    if not isinstance(questions, list):
        raise Exception(f"Expected JSON array, got: {type(questions)}")

    return questions


def parse_document_with_claude(document_text: str) -> list[dict[str, Any]]:
    """Parse document text into quiz questions using the Claude API."""
    client = _get_client()

    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        temperature=LLM_TEMPERATURE,
        messages=[
            {
                "role": "user",
                "content": f"Extract all questions from this document:\n\n{document_text}",
            },
        ],
    )

    return _parse_json_response(message.content[0].text)


_LLM_STRIP_FIELDS = {"image_data", "image_mime_type", "table_rows"}

MAX_RETRIES = 4
INITIAL_BACKOFF_S = 5.0


def _slim_items_for_llm(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a lightweight copy of items with large binary fields removed.

    The LLM only needs textual metadata (id, type, text, title,
    table_text_preview, source_url) to identify questions and context.
    Base64 image data and full table row arrays are stripped to drastically
    reduce token count.
    """
    slim: list[dict[str, Any]] = []
    for item in items:
        slim.append({k: v for k, v in item.items() if k not in _LLM_STRIP_FIELDS})
    return slim


def parse_document_items_with_claude(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Parse structured document items into quiz questions using the Claude API."""
    client = _get_client()

    slim_items = _slim_items_for_llm(items)
    serialized_items = json.dumps(slim_items, ensure_ascii=True)
    logger.info(
        "LLM payload: %d items, ~%d chars (original ~%d items)",
        len(slim_items),
        len(serialized_items),
        len(items),
    )

    system_instruction = (
        SYSTEM_PROMPT
        + "\n\nThe input is a JSON array of items from a Google Doc."
        + " Each item has id, type (paragraph, table, image, section), and"
        + " text/title/source_url fields."
        + " Extract questions and include context_ids referencing items"
        + " that should appear before each question. Use each question"
        + " only once; do not duplicate questions when context is split."
    )

    for attempt in range(MAX_RETRIES):
        try:
            message = client.messages.create(
                model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                system=system_instruction,
                temperature=LLM_TEMPERATURE,
                messages=[
                    {
                        "role": "user",
                        "content": f"Document items JSON:\n\n{serialized_items}",
                    },
                ],
            )
            return _parse_json_response(message.content[0].text)
        except (RateLimitError, APIStatusError) as exc:
            # Only retry on rate limits and server errors (5xx)
            if isinstance(exc, APIStatusError) and exc.status_code < 500:
                raise
            if attempt == MAX_RETRIES - 1:
                raise
            wait = min(INITIAL_BACKOFF_S * (2**attempt), 30.0)
            logger.warning(
                "Rate limited (attempt %d/%d). Retrying in %.0fs…",
                attempt + 1,
                MAX_RETRIES,
                wait,
            )
            time.sleep(wait)

    # All retries exhausted — the final attempt re-raises above
    raise RuntimeError("Retry loop exited without returning or raising")
