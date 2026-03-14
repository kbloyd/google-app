import logging
import os
import re
from typing import Any

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template_string,
    request,
    redirect,
    url_for,
    flash,
)

from services import google_service, parser, apps_script_client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
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

# Store questions in memory (in production, use Flask session)
_current_questions: list[dict[str, Any]] = []
_current_title: str = "Quiz from Google Doc"


@app.route("/")
def index():
    return render_template_string(
        HTML_TEMPLATE, apps_script_configured=apps_script_client.is_configured()
    )


@app.route("/convert", methods=["POST"])
def convert():
    global _current_questions, _current_title

    doc_url = request.form.get("doc_url", "").strip()

    if not doc_url:
        flash("Please provide a Google Doc URL")
        return redirect(url_for("index"))

    if not apps_script_client.is_configured():
        flash(
            "Apps Script Web App is not configured. Please add APPS_SCRIPT_WEB_APP_URL to your .env file."
        )
        return redirect(url_for("index"))

    try:
        doc_id = google_service.extract_doc_id(doc_url)
        doc_items = google_service.get_document_items(doc_id)
        doc_content = google_service.get_document_content(doc_id)
        doc_title = google_service.get_document_title(doc_id)

        if not doc_content or len(doc_content.strip()) < 10:
            flash("Document appears to be empty. Make sure the document has content.")
            return redirect(url_for("index"))

        questions = parser.parse_document_items_with_claude(doc_items)

        unique_questions: list[dict[str, Any]] = []
        seen_questions: set[str] = set()
        item_ids_in_order = [item["id"] for item in doc_items]
        item_by_id = {item["id"]: item for item in doc_items}
        item_id_to_index = {
            item_id: idx for idx, item_id in enumerate(item_ids_in_order)
        }

        answer_key_markers = {
            "answer key",
            "correct answer",
            "correct answers",
            "explanation",
            "solutions",
            "solution key",
        }

        def normalize_text(text: str) -> str:
            return " ".join(text.split()).casefold()

        def is_answer_key_text(text: str) -> bool:
            normalized = normalize_text(text)
            if not normalized:
                return False
            return any(marker in normalized for marker in answer_key_markers)

        def item_text_for_filter(item: dict[str, Any]) -> str:
            parts = [
                str(item.get("text") or ""),
                str(item.get("title") or ""),
                str(item.get("table_text_preview") or ""),
            ]
            return normalize_text(" ".join(part for part in parts if part))

        answer_key_start_index = len(item_ids_in_order)
        for item_id in item_ids_in_order:
            item = item_by_id[item_id]
            if item.get("type") not in {"section", "paragraph", "table", "image"}:
                continue
            if is_answer_key_text(item_text_for_filter(item)):
                answer_key_start_index = item_id_to_index[item_id]
                break

        eligible_item_ids = {
            item_id
            for item_id in item_ids_in_order
            if item_id_to_index[item_id] < answer_key_start_index
        }

        # --- Parse answer key table for quiz grading ---
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
                correct_ans = data_row[ans_col].strip() if ans_col < len(data_row) else ""
                explanation = ""
                if exp_col is not None and exp_col < len(data_row):
                    explanation = data_row[exp_col].strip()
                if correct_ans:
                    answer_key[q_num] = {
                        "correct_answer": correct_ans,
                        "explanation": explanation,
                    }

        # --- Parse paragraph-based answer keys (e.g., "1. B) 1985  2. C) Topps ...") ---
        if not answer_key:
            ak_paragraph_pattern = re.compile(
                r"(\d+)\.\s*([A-Da-d])\)\s*(.+?)(?=\s*\d+\.\s*[A-Da-d]\)|$)",
                re.DOTALL,
            )
            ak_text_parts: list[str] = []
            for item_id in item_ids_in_order:
                if item_id_to_index[item_id] < answer_key_start_index:
                    continue
                item = item_by_id[item_id]
                raw = str(item.get("text") or item.get("title") or "").strip()
                if raw:
                    ak_text_parts.append(raw)
            ak_full_text = " ".join(ak_text_parts)
            for m in ak_paragraph_pattern.finditer(ak_full_text):
                q_num = int(m.group(1))
                letter = m.group(2).upper()
                ans_text = m.group(3).strip()
                # Extract explanation from parenthetical if present
                explanation = ""
                paren_match = re.search(r"\((.+?)\)\s*$", ans_text)
                if paren_match:
                    explanation = paren_match.group(1).strip()
                    ans_text = ans_text[: paren_match.start()].strip()
                answer_key[q_num] = {
                    "correct_answer": f"{letter}) {ans_text}" if ans_text else letter,
                    "explanation": explanation,
                }

        paragraph_items: list[tuple[int, str]] = []
        for item_id in item_ids_in_order:
            if item_id not in eligible_item_ids:
                continue
            item = item_by_id[item_id]
            if item.get("type") in {"paragraph", "section"}:
                text_value = item.get("text") or item.get("title") or ""
                normalized = normalize_text(str(text_value))
                if normalized:
                    paragraph_items.append((item_id_to_index[item_id], normalized))
        for q in questions:
            question_text = str(q.get("question", "")).strip()
            if not question_text:
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

            question_index = None
            for idx, item_text in paragraph_items:
                if normalized and normalized in item_text:
                    question_index = idx
                    break
                if item_text and item_text in normalized:
                    question_index = idx
                    break

            if question_index is None:
                question_index = 0

            q["_question_index"] = question_index

            unique_questions.append(q)
        questions = unique_questions

        questions.sort(key=lambda item: item.get("_question_index", 0))

        # Merge consecutive questions that share identical option sets.
        # This handles LLM splitting a preamble + actual question into two entries.
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
                    normalize_text(str(o))
                    for o in q.get("options", [])
                    if str(o).strip()
                ]
                next_opts = [
                    normalize_text(str(o))
                    for o in next_q.get("options", [])
                    if str(o).strip()
                ]
                if q_opts and q_opts == next_opts:
                    q_text = str(q.get("question", ""))
                    next_text = str(next_q.get("question", ""))
                    # Keep the question that contains '?'; default to later one
                    if "?" in next_text:
                        keep, drop = next_q, q
                    elif "?" in q_text:
                        keep, drop = q, next_q
                    else:
                        keep, drop = next_q, q
                    # Adopt earlier anchor so context before the preamble attaches
                    keep["_question_index"] = min(
                        int(q.get("_question_index", 0)),
                        int(next_q.get("_question_index", 0)),
                    )
                    # Remember dropped text so it gets filtered as duplicate content
                    keep["_dropped_preamble"] = str(drop.get("question", ""))
                    merged_questions.append(keep)
                    skip_next = True
                    continue
            merged_questions.append(q)
        questions = merged_questions

        # Build a set of normalized question texts and option texts
        # so we can filter out context paragraphs that duplicate question/option content
        question_texts_set: set[str] = set()
        option_texts_set: set[str] = set()
        for q in questions:
            q_text = normalize_text(str(q.get("question", "")))
            if q_text:
                question_texts_set.add(q_text)
            # Include dropped preamble text so it gets filtered as duplicate
            preamble = normalize_text(str(q.pop("_dropped_preamble", "") or ""))
            if preamble:
                question_texts_set.add(preamble)
            for opt in q.get("options", []):
                opt_text = normalize_text(str(opt))
                if opt_text:
                    option_texts_set.add(opt_text)

        answer_label_pattern = re.compile(r"^[a-d]\)\s+", re.IGNORECASE)
        # Patterns for bullet/checkbox-style option lines: "● [ ] Option", "[ ] Option"
        bullet_checkbox_pattern = re.compile(
            r"^[●•\-\*\d.)\s]*\[[\sx]?\]\s*", re.IGNORECASE
        )
        # Pattern for numbered option prefixes: "1. Option", "2) Option"
        numbered_option_pattern = re.compile(r"^\d+[.)]\s+")
        # Doc-authoring tip pattern
        doc_tip_pattern = re.compile(
            r"^tip\s*:", re.IGNORECASE
        )

        def _strip_option_prefix(text: str) -> str:
            """Remove bullet, checkbox, number, and letter prefixes from text."""
            stripped = re.sub(r"^[●•\-\*]\s*", "", text)
            stripped = re.sub(r"^\[[\sx]?\]\s*", "", stripped)
            stripped = re.sub(r"^\d+[.)]\s+", "", stripped)
            stripped = re.sub(r"^[a-d]\)\s+", "", stripped, flags=re.IGNORECASE)
            return stripped.strip()

        # Pattern for leading question numbers: "6. ", "10. ", "4) "
        leading_number_pattern = re.compile(r"^\d+[.)]\s*")
        # Pattern for underscore-only filler lines (essay answer blanks)
        underscore_filler_pattern = re.compile(r"^[_\s]+$")

        def is_duplicate_content(item: dict[str, Any]) -> bool:
            """Check if a paragraph/section item duplicates question or option text."""
            if item["type"] not in {"paragraph", "section", "table", "image"}:
                return False
            text = item_text_for_filter(item)
            if not text:
                return False
            if is_answer_key_text(text):
                return True
            # Filter underscore-only filler lines (essay answer blanks)
            if underscore_filler_pattern.match(text):
                return True
            # Allow table-sourced images when they are before the answer-key
            # cutoff; only block tables whose preview contains answer-key markers.
            if item.get("type") == "image" and item.get("source_kind") == "table":
                preview = normalize_text(str(item.get("table_text_preview") or ""))
                if is_answer_key_text(preview):
                    return True
                return False
            # Also compare with leading number prefix stripped
            text_no_num = leading_number_pattern.sub("", text).strip()
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
            if answer_label_pattern.match(text):
                return True
            for t in texts_to_check:
                if t in option_texts_set:
                    return True
            # Strip bullet/checkbox/number prefixes and re-check against options
            stripped = _strip_option_prefix(text)
            if stripped and stripped in option_texts_set:
                return True
            # Skip doc-authoring tips referencing Google Docs features
            if doc_tip_pattern.match(text) and (
                "google docs" in text or "google doc" in text
            ):
                return True
            if text in {
                "mark only one oval",
                "mark only one oval.",
                "check all that apply",
                "check all that apply.",
            }:
                return True
            return False

        # --- Phase 1 + 4: Anchor-based, forward-correct context assignment ---
        # Build section boundaries for scoring
        section_starts: list[int] = [0]
        for item_id in item_ids_in_order:
            item = item_by_id[item_id]
            if item.get("type") == "section":
                section_starts.append(item_id_to_index[item_id])

        def _section_of(doc_index: int) -> int:
            """Return the section number an index belongs to."""
            sec = 0
            for s_idx, start in enumerate(section_starts):
                if doc_index >= start:
                    sec = s_idx
            return sec

        # Collect all eligible context items (not questions, not answer-key)
        context_item_ids = [
            item_id
            for item_id in item_ids_in_order
            if item_id in eligible_item_ids
            and item_by_id[item_id]["type"]
            in {"section", "paragraph", "image", "table"}
            and not is_duplicate_content(item_by_id[item_id])
        ]

        # Score each (context_item, question) pair; higher is better
        def _score_candidate(
            ctx_index: int, q_index: int, q_section: int
        ) -> tuple[int, int, int]:
            """Return (section_match, -distance, type_priority)."""
            ctx_section = _section_of(ctx_index)
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

        # Build question anchors
        q_anchors = [
            (idx, int(q.get("_question_index", 0))) for idx, q in enumerate(questions)
        ]

        # For each context item, find the best owning question:
        # - item must appear BEFORE the question anchor (forward-correct)
        # - prefer same section, closest distance, then type priority
        claim_map: dict[int, int] = {}  # context_item_id -> question_list_index
        for ctx_id in context_item_ids:
            ctx_index = item_id_to_index[ctx_id]
            best_q_idx: int | None = None
            best_score: tuple[int, int, int] | None = None
            for q_idx, q_anchor in q_anchors:
                if ctx_index >= q_anchor:
                    continue  # context must be before its question
                score = _score_candidate(
                    ctx_index, q_anchor, _section_of(q_anchor)
                )
                if best_score is None or score > best_score:
                    best_score = score
                    best_q_idx = q_idx
            # Fallback: if no question comes after, attach to nearest prior question
            if best_q_idx is None:
                for q_idx, q_anchor in reversed(q_anchors):
                    if q_anchor <= ctx_index:
                        best_q_idx = q_idx
                        break
            if best_q_idx is not None:
                claim_map[ctx_id] = best_q_idx

        # Assign context_ids per question in document order
        for idx, q in enumerate(questions):
            assigned = sorted(
                [
                    ctx_id
                    for ctx_id, owner_idx in claim_map.items()
                    if owner_idx == idx
                ],
                key=lambda cid: item_id_to_index[cid],
            )
            q["context_ids"] = assigned

        # --- Consolidate consecutive paragraph context items ---
        # Merge runs of adjacent paragraphs into a single item so they
        # appear as one block in the form instead of separate section headers.
        next_synthetic_id = max(item_ids_in_order) + 1
        for q in questions:
            ctx_ids = q.get("context_ids", [])
            if len(ctx_ids) <= 1:
                continue
            new_ctx_ids: list[int] = []
            paragraph_run: list[int] = []

            def _flush_paragraph_run() -> None:
                nonlocal next_synthetic_id
                if len(paragraph_run) <= 1:
                    new_ctx_ids.extend(paragraph_run)
                    return
                merged_text = "\n".join(
                    str(item_by_id[pid].get("text") or "")
                    for pid in paragraph_run
                )
                merged_item: dict[str, Any] = {
                    "id": next_synthetic_id,
                    "type": "paragraph",
                    "text": merged_text,
                }
                doc_items.append(merged_item)
                item_by_id[next_synthetic_id] = merged_item
                new_ctx_ids.append(next_synthetic_id)
                next_synthetic_id += 1

            for cid in ctx_ids:
                item = item_by_id[cid]
                if item["type"] == "paragraph":
                    paragraph_run.append(cid)
                else:
                    _flush_paragraph_run()
                    paragraph_run = []
                    new_ctx_ids.append(cid)
            _flush_paragraph_run()
            q["context_ids"] = new_ctx_ids

        # --- Phase 5: Debug trace (gated by DEBUG_CONTEXT env var) ---
        if os.getenv("DEBUG_CONTEXT"):
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
                logging.info(
                    "Q%d [anchor=%s]: %s\n  context_ids=%s\n%s",
                    idx,
                    q.get("_question_index", "?"),
                    q_text,
                    ctx_ids,
                    "\n".join(ctx_details) if ctx_details else "  (none)",
                )

        for q in questions:
            q.pop("_question_index", None)

        # --- Apply answer key to questions for quiz grading ---
        if answer_key:
            def _normalize_answer(text: str) -> str:
                """Strip leading option prefixes like 'B)', '2)', '2.', etc."""
                stripped = re.sub(r"^[A-Da-d0-9]+[.)]\s*", "", text).strip()
                return " ".join(stripped.split()).casefold()

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
                        if correct_norm in _normalize_answer(opt) or _normalize_answer(opt) in correct_norm:
                            matched_option = opt
                            break
                if matched_option:
                    q["correct_answer"] = matched_option
                    q["points"] = 1
                    if ak_entry.get("explanation"):
                        q["explanation"] = ak_entry["explanation"]

        if not questions:
            flash(
                "No questions found in the document. Make sure your document contains multiple choice questions."
            )
            return redirect(url_for("index"))

        # Store questions
        _current_questions = questions
        _current_title = doc_title or "Quiz from Google Doc"

        # Create form via Apps Script
        result = apps_script_client.create_form_with_items_via_apps_script(
            _current_title, doc_items, questions
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
