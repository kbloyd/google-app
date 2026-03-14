"""Client for Google Apps Script web app to create forms.

This bypasses the Forms API 500 error by using Apps Script instead.
"""

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 2.0


def _get_apps_script_url() -> str:
    """Return the configured Apps Script web-app URL."""
    return os.getenv("APPS_SCRIPT_WEB_APP_URL", "")


def _post_to_apps_script(payload: dict[str, Any]) -> dict[str, Any]:
    """Post *payload* to Apps Script with retry logic.

    Returns:
        A dict with ``formUrl``, ``editUrl``, ``formId``, and ``success``.

    Raises:
        ValueError: If the web-app URL is not configured.
        Exception: On non-retryable or exhausted-retry errors.
    """
    apps_script_url = _get_apps_script_url()
    if not apps_script_url:
        raise ValueError(
            "APPS_SCRIPT_WEB_APP_URL not configured. "
            "Please deploy the Apps Script and add the URL to your .env file."
        )

    secret = os.getenv("APPS_SCRIPT_SECRET", "")
    if secret:
        payload["secret"] = secret

    for attempt in range(_MAX_RETRIES):
        try:
            with httpx.Client(timeout=180.0, follow_redirects=True) as client:
                response = client.post(
                    apps_script_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )

            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"Server error: {response.status_code}",
                    request=response.request,
                    response=response,
                )

            if response.status_code != 200:
                raise Exception(
                    f"Apps Script error: {response.status_code} - "
                    f"{response.text[:500]}"
                )

            result = response.json()
            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                raise Exception(f"Apps Script failed: {error_msg}")

            return {
                "formUrl": result.get("formUrl"),
                "editUrl": result.get("editUrl"),
                "formId": result.get("formId"),
                "success": True,
            }
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.HTTPStatusError,
        ) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise
            wait = _INITIAL_BACKOFF * (2**attempt)
            logger.warning(
                "Apps Script call failed (attempt %d/%d): %s. "
                "Retrying in %.0fs...",
                attempt + 1,
                _MAX_RETRIES,
                str(exc)[:200],
                wait,
            )
            time.sleep(wait)

    raise RuntimeError("Unreachable")


def create_form_via_apps_script(
    title: str, questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create a Google Form using a deployed Apps Script web app.

    Args:
        title: The title for the new form.
        questions: List of question dicts with question, type, options, required.

    Returns:
        Dictionary with formUrl, editUrl, formId, and success status.
    """
    return _post_to_apps_script({"title": title, "questions": questions})


def create_form_with_items_via_apps_script(
    title: str, items: list[dict[str, Any]], questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create a Google Form with context items via Apps Script.

    Falls back to :func:`create_form_via_apps_script` when *items* is empty.

    Args:
        title: The title for the new form.
        items: Contextual items (images, tables, etc.) to embed in the form.
        questions: List of question dicts.

    Returns:
        Dictionary with formUrl, editUrl, formId, and success status.
    """
    if not items:
        return create_form_via_apps_script(title, questions)
    return _post_to_apps_script(
        {"title": title, "questions": questions, "items": items}
    )


def is_configured() -> bool:
    """Check if the Apps Script web app is configured."""
    return bool(_get_apps_script_url())
