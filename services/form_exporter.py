"""Export questions to formats that can be imported to Google Forms.

Google Forms supports importing questions from CSV/TSV files.
This module generates properly formatted import files.
"""

import csv
import io
from typing import Any


def export_to_form_import_csv(questions: list[dict[str, Any]]) -> str:
    """Export questions to a CSV format compatible with Google Forms import.

    Google Forms import format:
    - Question,Question Type (Multiple Choice/Checkbox),Option 1,Option 2,...

    Returns the CSV content as a string.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    # Write header
    writer.writerow(
        [
            "Question",
            "Question Type",
            "Option 1",
            "Option 2",
            "Option 3",
            "Option 4",
            "Option 5",
            "Option 6",
            "Required",
        ]
    )

    for q in questions:
        row = [
            q.get("question", ""),
            "Multiple Choice" if q.get("type") == "multiple_choice" else "Checkbox",
        ]

        # Add up to 6 options
        options = q.get("options", [])
        for i in range(6):
            row.append(options[i] if i < len(options) else "")

        row.append("Yes" if q.get("required") else "No")
        writer.writerow(row)

    return output.getvalue()


def export_to_form_import_tsv(questions: list[dict[str, Any]]) -> str:
    """Export questions to TSV format (tab-separated) for Google Forms import.

    Google Forms sometimes works better with TSV for importing.
    """
    lines = []

    # Header
    lines.append(
        "Question\tQuestion Type\tOption 1\tOption 2\tOption 3\tOption 4\tOption 5\tOption 6\tRequired"
    )

    for q in questions:
        parts = [
            q.get("question", ""),
            "Multiple Choice" if q.get("type") == "multiple_choice" else "Checkbox",
        ]

        options = q.get("options", [])
        for i in range(6):
            parts.append(options[i] if i < len(options) else "")

        parts.append("Yes" if q.get("required") else "No")
        lines.append("\t".join(parts))

    return "\n".join(lines)


def export_to_html_form(questions: list[dict[str, Any]], title: str) -> str:
    """Generate an HTML form that can be copied or saved.

    This creates a standalone HTML file with all questions formatted
    as a Google Forms-like interface.
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Google Sans', Roboto, Arial, sans-serif;
            background: #f0f2f5;
            margin: 0;
            padding: 20px;
            color: #202124;
        }}
        .form-container {{
            max-width: 640px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            border-top: 8px solid #4285f4;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 12px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 400;
            color: #202124;
        }}
        .question-card {{
            background: white;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 12px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }}
        .question-title {{
            font-size: 16px;
            font-weight: 500;
            margin-bottom: 16px;
            color: #202124;
        }}
        .question-title .required {{
            color: #d93025;
            margin-left: 4px;
        }}
        .options {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .option {{
            display: flex;
            align-items: center;
            padding: 8px;
            border-radius: 4px;
            cursor: pointer;
            transition: background-color 0.2s;
        }}
        .option:hover {{
            background: #f8f9fa;
        }}
        .option input {{
            margin-right: 12px;
            width: 20px;
            height: 20px;
        }}
        .option label {{
            flex: 1;
            font-size: 14px;
        }}
        .submit-btn {{
            background: #4285f4;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            margin-top: 12px;
        }}
        .submit-btn:hover {{
            background: #1557b0;
        }}
        .info {{
            background: #e8f0fe;
            border: 1px solid #4285f4;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="form-container">
        <div class="header">
            <h1>{title}</h1>
        </div>
        
        <div class="info">
            <strong>Note:</strong> This is a preview form. To import these questions into Google Forms:
            <ol>
                <li>Create a new Google Form</li>
                <li>Click the three dots menu (⋮) and select "Import questions"\u003c/li>
                <li>Upload the CSV file downloaded from this app\u003c/li>
            </ol>
        </div>
"""

    for i, q in enumerate(questions, 1):
        required = q.get("required", False)
        q_type = q.get("type", "multiple_choice")
        options = q.get("options", [])

        input_type = "checkbox" if q_type == "checkbox" else "radio"
        input_name = f"q{i}"

        required_span = ' <span class="required">*\u003c/span>' if required else ""

        html += f"""
        <div class="question-card">
            <div class="question-title">
                {i}. {q.get("question", "")}{required_span}
            </div>
            <div class="options">
"""

        for opt in options:
            html += f"""
                <div class="option">
                    <input type="{input_type}" name="{input_name}" id="{input_name}_{opt}">
                    <label for="{input_name}_{opt}">{opt}</label>
                </div>
"""

        html += "            </div>\n        </div>\n"

    html += """
        <button class="submit-btn" onclick="alert('This is a preview form. Use the CSV import method to create the actual Google Form.')">Submit</button>
    </div>
</body>
</html>"""

    return html
