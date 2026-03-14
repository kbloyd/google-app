import base64
import logging
import os
import threading
from io import BytesIO
from typing import Any

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

DISCOVERY_DOC_FORMS = "https://forms.googleapis.com/$discovery/rest?version=v1"
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

_credentials_lock = threading.Lock()
_cached_credentials: service_account.Credentials | None = None


def _get_cached_credentials() -> service_account.Credentials:
    """Return lazily-cached Google service-account credentials."""
    global _cached_credentials
    with _credentials_lock:
        if _cached_credentials is None or not _cached_credentials.valid:
            _cached_credentials = get_credentials()
        return _cached_credentials


def get_credentials() -> service_account.Credentials:
    private_key = os.getenv("GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY", "")
    private_key = private_key.replace("\\n", "\n")

    service_account_info = {
        "type": os.getenv("GOOGLE_SERVICE_ACCOUNT_TYPE"),
        "project_id": os.getenv("GOOGLE_SERVICE_ACCOUNT_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID"),
        "private_key": private_key,
        "client_email": os.getenv("GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_SERVICE_ACCOUNT_CLIENT_ID"),
        "auth_uri": os.getenv("GOOGLE_SERVICE_ACCOUNT_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_SERVICE_ACCOUNT_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_AUTH_PROVIDER_X509_CERT_URL"
        ),
        "client_x509_cert_url": os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_CLIENT_X509_CERT_URL"
        ),
        "universe_domain": os.getenv("GOOGLE_SERVICE_ACCOUNT_UNIVERSE_DOMAIN"),
    }

    required_fields = [
        "type",
        "project_id",
        "private_key",
        "client_email",
        "token_uri",
    ]
    for field in required_fields:
        if not service_account_info.get(field):
            raise ValueError(
                f"Missing required environment variable: GOOGLE_SERVICE_ACCOUNT_{field.upper()}"
            )

    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/forms.body",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=scopes
    )
    return credentials


def get_docs_service():
    """Build and return a Google Docs API service client."""
    credentials = _get_cached_credentials()
    service = discovery.build("docs", "v1", credentials=credentials)
    return service


def get_forms_service():
    """Build and return a Google Forms API service client."""
    credentials = _get_cached_credentials()
    service = discovery.build(
        "forms",
        "v1",
        credentials=credentials,
        discoveryServiceUrl=DISCOVERY_DOC_FORMS,
        static_discovery=False,
    )
    return service


def extract_doc_id(url: str) -> str:
    if "/d/" in url:
        start = url.index("/d/") + 3
        if "/edit" in url:
            end = url.index("/edit")
        else:
            end = len(url)
        return url[start:end]
    return url


def _extract_paragraph_text(paragraph: dict[str, Any]) -> str:
    parts: list[str] = []
    for prop in paragraph.get("elements", []):
        if "textRun" in prop:
            parts.append(prop["textRun"].get("content", ""))
        elif "inlineObjectElement" in prop:
            parts.append("[Image]")
        elif "footnoteReference" in prop:
            parts.append("[Footnote]")
    return "".join(parts)


def _extract_structural_element_text(element: dict[str, Any]) -> list[str]:
    text_chunks: list[str] = []

    if "paragraph" in element:
        paragraph = element.get("paragraph", {})
        text_chunks.append(_extract_paragraph_text(paragraph))
    elif "table" in element:
        table = element.get("table", {})
        for row in table.get("tableRows", []):
            row_text: list[str] = []
            for cell in row.get("tableCells", []):
                cell_parts: list[str] = []
                for cell_elem in cell.get("content", []):
                    cell_parts.extend(_extract_structural_element_text(cell_elem))
                row_text.append("".join(cell_parts).strip())
            text_chunks.append(" | ".join(row_text))
    elif "tableOfContents" in element:
        toc = element.get("tableOfContents", {})
        for toc_elem in toc.get("content", []):
            text_chunks.extend(_extract_structural_element_text(toc_elem))
    elif "sectionBreak" in element:
        text_chunks.append("\n")

    return text_chunks


def _get_inline_object_details(
    inline_objects: dict[str, Any], inline_object_id: str
) -> tuple[str | None, str | None]:
    inline_object = inline_objects.get(inline_object_id, {})
    props = inline_object.get("inlineObjectProperties", {})
    embedded = props.get("embeddedObject", {})
    image_props = embedded.get("imageProperties", {})
    url = image_props.get("contentUri")
    title = embedded.get("title") or embedded.get("description")
    return url, title


def _fetch_image_data(
    session: AuthorizedSession, url: str
) -> tuple[str | None, str | None]:
    """Fetch image from *url* via *session* and return (base64_data, mime_type).

    Returns ``(None, None)`` when the image cannot be fetched or exceeds
    :data:`MAX_IMAGE_SIZE`.
    """
    try:
        # HEAD request first to check size without downloading
        head_resp = session.head(url)
        content_length = int(head_resp.headers.get("Content-Length", 0))
        if content_length > MAX_IMAGE_SIZE:
            logger.warning(
                "Skipping oversized image (%d bytes): %s",
                content_length,
                url[:100],
            )
            return None, None

        response = session.get(url)
        if response.status_code != 200:
            logger.warning(
                "Image fetch failed (HTTP %d): %s",
                response.status_code,
                url[:100],
            )
            return None, None

        if len(response.content) > MAX_IMAGE_SIZE:
            logger.warning(
                "Skipping oversized image (%d bytes): %s",
                len(response.content),
                url[:100],
            )
            return None, None

        content_type = response.headers.get("Content-Type", "image/png")
        data_b64 = base64.b64encode(response.content).decode("ascii")
        return data_b64, content_type
    except (ConnectionError, TimeoutError, OSError) as exc:
        logger.warning("Image fetch error: %s - %s", type(exc).__name__, url[:100])
        return None, None


def _find_monospace_font_path() -> str | None:
    """Return the path to the first available monospace font, or ``None``."""
    candidates = [
        # macOS
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Courier.ttc",
        "/Library/Fonts/Courier New.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        # Windows
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _render_table_image(rows: list[list[str]]) -> tuple[str, str]:
    padding_x = 16
    padding_y = 12
    line_padding = 8
    font_size = 28

    font_path = _find_monospace_font_path()
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        font = ImageFont.load_default()

    column_count = max(len(row) for row in rows)
    col_widths = [0] * column_count
    for row in rows:
        for idx, cell in enumerate(row):
            cell_text = str(cell)
            width = font.getlength(cell_text)
            col_widths[idx] = max(col_widths[idx], int(width))

    table_width = int(sum(col_widths) + (column_count - 1) * 24)
    row_height = font_size + line_padding
    table_height = len(rows) * row_height

    image_width = table_width + padding_x * 2
    image_height = table_height + padding_y * 2

    image = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(image)

    y = padding_y
    for row_index, row in enumerate(rows):
        x = padding_x
        for idx in range(column_count):
            cell_text = str(row[idx]) if idx < len(row) else ""
            draw.text((x, y), cell_text, fill="black", font=font)
            x += col_widths[idx] + 24
        y += row_height
        if row_index == 0:
            line_y = y - line_padding // 2
            draw.line(
                (padding_x, line_y, image_width - padding_x, line_y),
                fill="#999999",
                width=2,
            )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    data_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return data_b64, "image/png"


def _build_table_text_preview(rows: list[list[str]], max_rows: int = 3) -> str:
    preview_rows = rows[:max_rows]
    preview_lines = [" | ".join(str(cell).strip() for cell in row) for row in preview_rows]
    return "\n".join(line for line in preview_lines if line.strip())


def _extract_paragraph_items(
    paragraph: dict[str, Any],
    inline_objects: dict[str, Any],
    inline_object_cache: dict[str, dict[str, Any]],
    session: AuthorizedSession,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    paragraph_style = paragraph.get("paragraphStyle", {})
    named_style = paragraph_style.get("namedStyleType", "")
    is_heading = named_style.startswith("HEADING_")

    text_parts: list[str] = []

    def flush_text() -> None:
        text = "".join(text_parts).strip()
        text_parts.clear()
        if not text:
            return
        if is_heading:
            items.append({"type": "section", "title": text})
        else:
            items.append({"type": "paragraph", "text": text})

    for prop in paragraph.get("elements", []):
        if "textRun" in prop:
            text_parts.append(prop["textRun"].get("content", ""))
        elif "inlineObjectElement" in prop:
            flush_text()
            inline_object_id = prop["inlineObjectElement"].get("inlineObjectId")
            if inline_object_id:
                cached = inline_object_cache.get(inline_object_id)
                if cached is None:
                    url, title = _get_inline_object_details(
                        inline_objects, inline_object_id
                    )
                    cached = {"source_url": url, "title": title}
                    if url:
                        data_b64, mime_type = _fetch_image_data(session, url)
                        if data_b64 and mime_type:
                            cached["image_data"] = data_b64
                            cached["image_mime_type"] = mime_type
                    inline_object_cache[inline_object_id] = cached
                if cached.get("source_url"):
                    item = {
                        "type": "image",
                        "source_url": cached.get("source_url"),
                    }
                    if cached.get("title"):
                        item["title"] = cached.get("title")
                    if cached.get("image_data"):
                        item["image_data"] = cached.get("image_data")
                    if cached.get("image_mime_type"):
                        item["image_mime_type"] = cached.get("image_mime_type")
                    items.append(item)
                else:
                    items.append({"type": "paragraph", "text": "[Image]"})
        elif "footnoteReference" in prop:
            continue

    flush_text()
    return items


def _extract_structural_items(
    element: dict[str, Any],
    inline_objects: dict[str, Any],
    inline_object_cache: dict[str, dict[str, Any]],
    session: AuthorizedSession,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if "paragraph" in element:
        items.extend(
            _extract_paragraph_items(
                element.get("paragraph", {}),
                inline_objects,
                inline_object_cache,
                session,
            )
        )
    elif "table" in element:
        table = element.get("table", {})
        table_rows: list[list[str]] = []
        for row in table.get("tableRows", []):
            row_cells: list[str] = []
            for cell in row.get("tableCells", []):
                cell_content: list[str] = []
                for cell_elem in cell.get("content", []):
                    if "paragraph" in cell_elem:
                        cell_content.append(
                            _extract_paragraph_text(cell_elem.get("paragraph", {}))
                        )
                row_cells.append(
                    " ".join(part.strip() for part in cell_content if part)
                )
            if any(cell.strip() for cell in row_cells):
                table_rows.append(row_cells)

        if len(table_rows) == 1:
            table_text = " | ".join(table_rows[0])
            if table_text:
                items.append({"type": "table", "text": table_text})
        elif len(table_rows) > 1:
            image_data, image_mime_type = _render_table_image(table_rows)
            table_preview = _build_table_text_preview(table_rows)
            items.append(
                {
                    "type": "image",
                    "title": "",
                    "image_data": image_data,
                    "image_mime_type": image_mime_type,
                    "source_kind": "table",
                    "table_row_count": len(table_rows),
                    "table_col_count": max(len(row) for row in table_rows),
                    "table_text_preview": table_preview,
                    "table_rows": table_rows,
                }
            )
    elif "tableOfContents" in element:
        toc = element.get("tableOfContents", {})
        for toc_elem in toc.get("content", []):
            items.extend(
                _extract_structural_items(
                    toc_elem,
                    inline_objects,
                    inline_object_cache,
                    session,
                )
            )

    return items


def get_document(doc_id: str) -> dict[str, Any]:
    """Fetch a Google Doc once and return items, content, and title.

    Returns:
        A dict with keys ``items``, ``content``, and ``title``.
    """
    credentials = _get_cached_credentials()
    service = discovery.build("docs", "v1", credentials=credentials)
    doc = service.documents().get(documentId=doc_id).execute()

    title = doc.get("title", "Quiz from Google Doc")
    content_elements = doc.get("body", {}).get("content", [])
    inline_objects = doc.get("inlineObjects", {})
    session = AuthorizedSession(credentials)

    # Extract text content
    text_chunks: list[str] = []
    for element in content_elements:
        text_chunks.extend(_extract_structural_element_text(element))
    content = "\n".join(chunk for chunk in text_chunks if chunk)

    # Extract structured items
    inline_object_cache: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    for element in content_elements:
        items.extend(
            _extract_structural_items(
                element, inline_objects, inline_object_cache, session
            )
        )
    for idx, item in enumerate(items, start=1):
        item["id"] = idx

    return {"items": items, "content": content, "title": title}


def get_document_content(doc_id: str) -> str:
    """Return the plain-text content of a Google Doc."""
    return get_document(doc_id)["content"]


def get_document_title(doc_id: str) -> str:
    """Return the title of a Google Doc."""
    return get_document(doc_id)["title"]


def get_document_items(doc_id: str) -> list[dict[str, Any]]:
    """Return the structured items extracted from a Google Doc."""
    return get_document(doc_id)["items"]


def create_form(title: str, questions: list[dict[str, Any]]) -> str:
    """Create a Google Form using the Forms API.

    Note: This requires the Forms API to be enabled and working.
    If you get 500 errors, use create_form_spreadsheet() as a fallback.
    """
    service = get_forms_service()

    form_info = {"info": {"title": title}}
    form = service.forms().create(body=form_info).execute()
    form_id = form.get("formId")

    for idx, q in enumerate(questions):
        question_request = {
            "createItem": {
                "item": {
                    "title": q["question"],
                    "questionItem": {
                        "question": {
                            "required": q.get("required", False),
                        }
                    },
                },
                "location": {"index": idx},
            }
        }

        q_type = q.get("type", "multiple_choice")
        options = q.get("options", [])

        if q_type == "multiple_choice" and options:
            question_request["createItem"]["item"]["questionItem"]["question"][
                "choiceQuestion"
            ] = {
                "type": "RADIO",
                "options": [{"value": opt} for opt in options],
                "shuffle": False,
            }
        elif q_type == "checkbox" and options:
            question_request["createItem"]["item"]["questionItem"]["question"][
                "choiceQuestion"
            ] = {
                "type": "CHECKBOX",
                "options": [{"value": opt} for opt in options],
                "shuffle": False,
            }
        else:
            question_request["createItem"]["item"]["questionItem"]["question"][
                "textQuestion"
            ] = {}

        service.forms().batchUpdate(
            formId=form_id, body={"requests": [question_request]}
        ).execute()

    return f"https://docs.google.com/forms/d/{form_id}/viewform"


def create_form_spreadsheet(title: str, questions: list[dict[str, Any]]) -> str:
    """Create a Google Sheet with questions that can be imported to Forms.

    This is a fallback when the Forms API returns 500 errors.
    The spreadsheet uses a format that can be imported to Google Forms
    using Forms > Import questions feature.

    Returns the URL of the created spreadsheet.
    """
    credentials = get_credentials()

    # Build Sheets service (Forms API scope also works for Sheets)
    sheets_service = discovery.build("sheets", "v4", credentials=credentials)

    # Create spreadsheet
    spreadsheet_body = {
        "properties": {"title": f"{title} - Import to Forms"},
        "sheets": [
            {
                "properties": {
                    "title": "Questions",
                    "gridProperties": {
                        "rowCount": len(questions) + 2,
                        "columnCount": 10,
                    },
                }
            }
        ],
    }

    spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet_body).execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]
    spreadsheet_url = spreadsheet["spreadsheetUrl"]

    # Build data rows
    rows = [
        ["Question", "Type", "Option 1", "Option 2", "Option 3", "Option 4", "Required"]
    ]

    for q in questions:
        row = [
            q.get("question", ""),
            "Multiple Choice" if q.get("type") == "multiple_choice" else "Checkbox",
        ]

        options = q.get("options", [])
        for i in range(4):
            row.append(options[i] if i < len(options) else "")

        row.append("Yes" if q.get("required") else "No")
        rows.append(row)

    # Write data to sheet
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Questions!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    return spreadsheet_url
