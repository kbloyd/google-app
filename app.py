import logging
import os
from typing import Any

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template_string,
    request,
    url_for,
)
from googleapiclient.errors import HttpError

from services import (
    apps_script_client,
    answer_key_parser,
    context_assigner,
    google_service,
    parser,
    question_processor,
)
from services.constants import ANSWER_NORMALIZE_PATTERN

load_dotenv()

app = Flask(__name__)
_secret_key = os.getenv("SECRET_KEY", "")
if not _secret_key and os.getenv("RENDER", ""):
    raise RuntimeError("SECRET_KEY must be set in production")
app.secret_key = _secret_key or "dev-secret-key-change-in-production"
logging.basicConfig(level=logging.INFO)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google Doc to Form Converter</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            width: 100%;
            max-width: 700px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #444;
            font-weight: 500;
        }
        input[type="text"] {
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 14px 32px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
        }
        .btn:disabled {
            opacity: 0.7;
            cursor: not-allowed;
            transform: none;
        }
        .result {
            margin-top: 30px;
            padding: 20px;
            background: #f0f9f0;
            border-radius: 8px;
            border-left: 4px solid #4caf50;
        }
        .result h3 {
            color: #2e7d32;
            margin-bottom: 10px;
        }
        .result a {
            color: #1976d2;
            word-break: break-all;
            font-size: 16px;
            font-weight: 500;
        }
        .result a:hover {
            text-decoration: underline;
        }
        .error {
            background: #fff0f0;
            border-left-color: #f44336;
            color: #c62828;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .info {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 13px;
            color: #666;
        }
        .success-banner {
            background: #e8f5e9;
            border-left: 4px solid #4caf50;
            color: #2e7d32;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
            vertical-align: middle;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .questions-preview {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .question-item {
            margin-bottom: 15px;
            padding: 10px;
            background: white;
            border-radius: 6px;
            border-left: 3px solid #667eea;
        }
        .question-text {
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }
        .options-list {
            color: #666;
            font-size: 14px;
        }
        .option-item {
            margin: 4px 0;
            padding-left: 15px;
        }
        .option-item::before {
            content: "○";
            margin-right: 8px;
            color: #999;
        }
        .form-links {
            margin-top: 15px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .form-link-btn {
            display: inline-block;
            padding: 10px 20px;
            background: #4285f4;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            transition: background 0.2s;
        }
        .form-link-btn:hover {
            background: #3367d6;
        }
        .form-link-btn.secondary {
            background: #fff;
            color: #4285f4;
            border: 2px solid #4285f4;
        }
        .form-link-btn.secondary:hover {
            background: #f5f5f5;
        }
        code {
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
        .config-status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
            margin-left: 10px;
        }
        .config-status.ok {
            background: #e8f5e9;
            color: #2e7d32;
        }
        .config-status.warning {
            background: #fff8e1;
            color: #f57c00;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Doc to Form Converter 
            {% if apps_script_configured %}
            <span class="config-status ok">✓ Apps Script Ready</span>
            {% else %}
            <span class="config-status warning">⚠ Config Required</span>
            {% endif %}
        </h1>
        <p class="subtitle">Convert your Google Doc quiz into a Google Form instantly</p>
        
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="error">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% if not apps_script_configured %}
        <div class="info" style="background: #fff8e1; border-left: 4px solid #ffc107;">
            <strong>Setup Required:</strong> Apps Script Web App is not configured.
            Please add <code>APPS_SCRIPT_WEB_APP_URL</code> to your .env file.
        </div>
        {% endif %}
        
        <form method="POST" action="/convert">
            <div class="form-group">
                <label for="doc_url">Google Doc Link</label>
                <input type="text" id="doc_url" name="doc_url" placeholder="https://docs.google.com/document/d/..." required>
            </div>
            
            <div class="info">
                <strong>Important:</strong> Share your document with 
                <code>doc-to-form@doc-to-form-converter.iam.gserviceaccount.com</code> 
                with "Viewer" access before converting.
            </div>
            
            <button type="submit" class="btn" id="submitBtn" {% if not apps_script_configured %}disabled{% endif %}>
                <span class="spinner" id="spinner" style="display:none;"></span>
                <span id="btnText">Convert to Google Form</span>
            </button>
        </form>
        
        {% if questions %}
        <div class="questions-preview">
            <h3>Extracted Questions ({{ questions|length }} found)</h3>
            {% for q in questions %}
            <div class="question-item">
                <div class="question-text">{{ q.question }}</div>
                <div class="options-list">
                    {% for opt in q.options %}
                    <div class="option-item">{{ opt }}</div>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if form_url %}
        <div class="result">
            <h3>Form Created Successfully!</h3>
            <p>Your Google Form is ready:</p>
            <p><a href="{{ form_url }}" target="_blank">{{ form_url }}</a></p>
            
            <div class="form-links">
                <a href="{{ form_url }}" target="_blank" class="form-link-btn">View Form</a>
                {% if edit_url %}
                <a href="{{ edit_url }}" target="_blank" class="form-link-btn secondary">Edit Form</a>
                {% endif %}
            </div>
        </div>
        {% endif %}
    </div>
    
    <script>
        document.querySelector('form').addEventListener('submit', function() {
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('spinner').style.display = 'inline-block';
            document.getElementById('btnText').textContent = 'Creating Form...';
        });
    </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Normalize whitespace and case-fold text for comparison."""
    return " ".join(text.split()).casefold()


def _is_answer_key_text(text: str) -> bool:
    """Check if text appears to be an answer key header."""
    from services.constants import ANSWER_KEY_MARKERS

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


def _normalize_answer(text: str) -> str:
    """Strip leading option prefixes like 'B)', '2)', '2.', etc."""
    stripped = ANSWER_NORMALIZE_PATTERN.sub("", text).strip()
    return " ".join(stripped.split()).casefold()


def _find_answer_key_boundary(
    item_ids_in_order: list[int],
    item_by_id: dict[int, dict[str, Any]],
    item_id_to_index: dict[int, int],
) -> int:
    """Return the doc index where the answer-key section starts."""
    for item_id in item_ids_in_order:
        item = item_by_id[item_id]
        if item.get("type") not in {"section", "paragraph", "table", "image"}:
            continue
        if _is_answer_key_text(_item_text_for_filter(item)):
            return item_id_to_index[item_id]
    return len(item_ids_in_order)


def _apply_answer_key(
    questions: list[dict[str, Any]],
    answer_key: dict[int, dict[str, str]],
) -> None:
    """Match answer-key entries to questions and set grading fields."""
    if not answer_key:
        return
    for q_idx, q in enumerate(questions, start=1):
        ak_entry = answer_key.get(q_idx)
        if not ak_entry:
            continue
        options = q.get("options") or []
        if not options:
            continue
        correct_raw = ak_entry["correct_answer"]
        correct_norm = _normalize_answer(correct_raw)
        matched_option = None
        for opt in options:
            if _normalize_answer(opt) == correct_norm:
                matched_option = opt
                break
        if matched_option is None:
            for opt in options:
                opt_norm = _normalize_answer(opt)
                if correct_norm in opt_norm or opt_norm in correct_norm:
                    matched_option = opt
                    break
        if matched_option:
            q["correct_answer"] = matched_option
            q["points"] = 1
            if ak_entry.get("explanation"):
                q["explanation"] = ak_entry["explanation"]


@app.route("/")
def index():
    return render_template_string(
        HTML_TEMPLATE, apps_script_configured=apps_script_client.is_configured()
    )


@app.route("/convert", methods=["POST"])
def convert():
    doc_url = request.form.get("doc_url", "").strip()

    if not doc_url:
        flash("Please provide a Google Doc URL")
        return redirect(url_for("index"))

    if not apps_script_client.is_configured():
        flash(
            "Apps Script Web App is not configured. "
            "Please add APPS_SCRIPT_WEB_APP_URL to your .env file."
        )
        return redirect(url_for("index"))

    try:
        doc_id = google_service.extract_doc_id(doc_url)
        doc_data = google_service.get_document(doc_id)
        doc_items = doc_data["items"]
        doc_content = doc_data["content"]
        doc_title = doc_data["title"]

        if not doc_content or len(doc_content.strip()) < 10:
            flash("Document appears to be empty. Make sure the document has content.")
            return redirect(url_for("index"))

        questions = parser.parse_document_items_with_claude(doc_items)

        # Build indexes
        item_ids_in_order = [item["id"] for item in doc_items]
        item_by_id = {item["id"]: item for item in doc_items}
        item_id_to_index = {
            item_id: idx for idx, item_id in enumerate(item_ids_in_order)
        }

        # Find answer key boundary
        answer_key_start_index = _find_answer_key_boundary(
            item_ids_in_order, item_by_id, item_id_to_index
        )
        eligible_item_ids = {
            iid
            for iid in item_ids_in_order
            if item_id_to_index[iid] < answer_key_start_index
        }

        # Parse answer key
        answer_key = answer_key_parser.parse_answer_key(
            item_ids_in_order, item_by_id, item_id_to_index, answer_key_start_index
        )

        # Build paragraph items for anchoring
        paragraph_items: list[tuple[int, str]] = []
        for item_id in item_ids_in_order:
            if item_id not in eligible_item_ids:
                continue
            item = item_by_id[item_id]
            if item.get("type") in {"paragraph", "section"}:
                text_value = item.get("text") or item.get("title") or ""
                normalized = _normalize_text(str(text_value))
                if normalized:
                    paragraph_items.append((item_id_to_index[item_id], normalized))

        # Process questions (dedup, validate, sort, merge)
        seen_questions: set[str] = set()
        questions = question_processor.process_questions(
            questions, paragraph_items, seen_questions
        )

        # Build dedup sets for context filtering
        question_texts_set, option_texts_set = (
            question_processor.build_dedup_sets(questions)
        )

        # Assign context items to questions
        context_assigner.assign_context(
            questions,
            doc_items,
            eligible_item_ids,
            item_by_id,
            item_id_to_index,
            item_ids_in_order,
            question_texts_set,
            option_texts_set,
        )

        for q in questions:
            q.pop("_question_index", None)

        # Apply answer key for quiz grading
        _apply_answer_key(questions, answer_key)

        if not questions:
            flash(
                "No questions found in the document. "
                "Make sure your document contains multiple choice questions."
            )
            return redirect(url_for("index"))

        # Create form via Apps Script
        form_title = doc_title or "Quiz from Google Doc"
        result = apps_script_client.create_form_with_items_via_apps_script(
            form_title, doc_items, questions
        )

        if result.get("success"):
            return render_template_string(
                HTML_TEMPLATE,
                questions=questions,
                form_url=result.get("formUrl"),
                edit_url=result.get("editUrl"),
                apps_script_configured=True,
            )
        else:
            flash(f"Failed to create form: {result.get('error', 'Unknown error')}")
            return render_template_string(
                HTML_TEMPLATE, questions=questions, apps_script_configured=True
            )

    except ValueError as e:
        flash(str(e))
        return redirect(url_for("index"))
    except HttpError as e:
        logging.exception("Google API error")
        if e.resp.status == 404:
            flash("Document not found. Check the URL and sharing permissions.")
        elif e.resp.status == 403:
            flash(
                "Access denied. Make sure the document is shared "
                "with the service account."
            )
        else:
            flash(f"Google API error: {e.resp.status}")
        return redirect(url_for("index"))
    except Exception as e:
        logging.exception("Conversion failed")
        flash(f"Error: {str(e)}")
        return redirect(url_for("index"))


if __name__ == "__main__":
    import socket

    port = 5000
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
            break
        except OSError:
            port += 1
    print(f"Starting Flask on port {port}")
    print(f"Apps Script configured: {apps_script_client.is_configured()}")
    app.run(debug=True, host="0.0.0.0", port=port)
