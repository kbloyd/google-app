"""Client for Google Apps Script web app to create forms.

This bypasses the Forms API 500 error by using Apps Script instead.
"""

import json
import os
from typing import Any

import httpx


def _get_apps_script_url() -> str:
    return os.getenv("APPS_SCRIPT_WEB_APP_URL", "")


def create_form_via_apps_script(
    title: str, questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create a Google Form using a deployed Apps Script web app.

    Args:
        title: The title for the new form
        questions: List of question dictionaries with question, type, options, required

    Returns:
        Dictionary with formUrl, editUrl, formId, and success status

    Raises:
        ValueError: If APPS_SCRIPT_WEB_APP_URL is not configured
        Exception: If the API call fails
    """
    apps_script_url = _get_apps_script_url()
    if not apps_script_url:
        raise ValueError(
            "APPS_SCRIPT_WEB_APP_URL not configured. "
            "Please deploy the Apps Script and add the URL to your .env file."
        )

    payload = {
        "title": title,
        "questions": questions,
    }

    # Follow redirects - Apps Script redirects to a different URL
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.post(
            apps_script_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    if response.status_code != 200:
        raise Exception(
            f"Apps Script error: {response.status_code} - {response.text[:500]}"
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


def create_form_with_items_via_apps_script(
    title: str, items: list[dict[str, Any]], questions: list[dict[str, Any]]
) -> dict[str, Any]:
    if not items:
        return create_form_via_apps_script(title, questions)

    apps_script_url = _get_apps_script_url()
    if not apps_script_url:
        raise ValueError(
            "APPS_SCRIPT_WEB_APP_URL not configured. "
            "Please deploy the Apps Script and add the URL to your .env file."
        )

    payload = {
        "title": title,
        "questions": questions,
        "items": items,
    }

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.post(
            apps_script_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    if response.status_code != 200:
        raise Exception(
            f"Apps Script error: {response.status_code} - {response.text[:500]}"
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


def is_configured() -> bool:
    """Check if the Apps Script web app is configured."""
    return bool(_get_apps_script_url())
