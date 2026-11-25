"""Review Agent backend for LearnDataAI.

Owners: Mack Jackson and Latonya Smith

The Review Agent has two halves:

  PART 1 - EVIDENCE ANALYSIS (Mack Jackson)        <- implemented in this file
      Reads an uploaded chart, graph, or R output (PNG, JPG, JPEG, or PDF),
      sends it to the OpenAI multimodal API, and returns a structured
      "evidence" dictionary describing only what is visible in the file.

  PART 2 - INTERPRETATION EVALUATION (Latonya Smith)  <- not yet implemented;
      reserved section at the bottom of this file. Will compare the student's
      interpretation against the evidence and the instructor rubric.

Public entry point for Part 1:

    analyze_evidence(file_bytes, filename, mime_type=None,
                     client=None, model=None) -> dict

See EVIDENCE CONTRACT below for the exact shape of the returned dictionary.

API key: read from the OPENAI_API_KEY environment variable or Streamlit
secrets (.streamlit/secrets.toml locally, the app's Secrets settings on
Streamlit Community Cloud). The key is never stored in this file.
Optional: OPENAI_MODEL overrides the default vision model.
"""

from __future__ import annotations

import base64
import io
import json
import os

from PIL import Image, ImageFilter, ImageOps, ImageStat

# =============================================================================
# PART 1 - EVIDENCE ANALYSIS (Mack Jackson)
# =============================================================================

DEFAULT_MODEL = "gpt-5.4-mini"
SUPPORTED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

MAX_PDF_PAGES = 5          # Only the first pages of long PDFs are analyzed.
PDF_RENDER_ZOOM = 2.0      # 2.0 = about 144 DPI, enough for axis tick labels.
MAX_IMAGE_SIDE = 2048      # Larger images are downscaled before upload.
MIN_READABLE_SIDE = 300    # Below this, small text is usually unreadable.
BLUR_THRESHOLD = 600.0     # Edge-strength score below this suggests blur.

# -----------------------------------------------------------------------------
# EVIDENCE CONTRACT (what analyze_evidence returns)
#
# Latonya: this is the dictionary your evaluation functions receive. Every
# top-level key is always present, on success and on error. Inside "evidence",
# lists may be empty and fields marked "| None" are None when something is not
# shown or cannot be read; the model is instructed never to guess.
#
# {
#   "status": "ok" | "error",
#   "error": str | None,               # message when status == "error"
#   "source": {
#       "filename": str,
#       "file_kind": "image" | "pdf" | None,   # None on error
#       "pages_analyzed": int,          # 1 for images, up to MAX_PDF_PAGES
#                                       # for PDFs, 0 on error
#       "pdf_text": str | None,         # embedded PDF text (useful for R output);
#                                       # None for images and scanned PDFs
#   },
#   "local_quality_checks": [           # computed without the API (Pillow);
#                                       # empty list on error
#       {"page": int, "width": int, "height": int,
#        "sharpness_score": float,
#        "flags": [str, ...]}           # "low_resolution", "possibly_blurry"
#   ],
#   "evidence": {                       # produced by the model; enforced by
#                                       # EVIDENCE_SCHEMA below
#       "content_type": "chart" | "r_output" | "chart_and_r_output" | "other" | "unreadable",
#       "chart_type": str | None,       # e.g. "scatterplot", "histogram"
#       "title": str | None,
#       "axes": [{"axis", "label", "units", "scale", "range"}],
#       "legend": [{"label", "meaning"}],
#       "variables": [str],
#       "trends": [str],                # patterns and relationships
#       "statistical_values": [{"name", "value", "location"}],  # copied verbatim
#       "outliers": [str],
#       "r_output": {"code": [str], "results": [str], "warnings": [str], "errors": [str]},
#       "quality_issues": [{"type", "description"}],
#       "unreadable_elements": [str],
#       "overall_confidence": "high" | "medium" | "low",  # forced to "low" when
#                                       # the local check flags blur or low resolution.
#   On blurry files, title, axis label/units/range, and statistical_values
#   are None/empty and their possible readings are listed in
#   unreadable_elements as "(unverified, image blurry)".
#       "summary": str,
#   },
#   "model": str,                      # model name used for the request
# }
#
# When status == "error", "evidence" is None and app.py shows result["error"].
# app.py also adds a "file_key" (SHA-256 of the upload) to the stored result
# so it can skip re-analyzing the same file; it is not part of this contract.
# -----------------------------------------------------------------------------

_NULLABLE_STRING = {"type": ["string", "null"]}

# JSON schema enforced by OpenAI Structured Outputs so the response always
# parses and always has every field above.
EVIDENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "content_type": {
            "type": "string",
            "enum": ["chart", "r_output", "chart_and_r_output", "other", "unreadable"],
        },
        "chart_type": _NULLABLE_STRING,
        "title": _NULLABLE_STRING,
        "axes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "axis": {"type": "string"},
                    "label": _NULLABLE_STRING,
                    "units": _NULLABLE_STRING,
                    "scale": _NULLABLE_STRING,
                    "range": _NULLABLE_STRING,
                },
                "required": ["axis", "label", "units", "scale", "range"],
            },
        },
        "legend": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"label": {"type": "string"}, "meaning": _NULLABLE_STRING},
                "required": ["label", "meaning"],
            },
        },
        "variables": {"type": "array", "items": {"type": "string"}},
        "trends": {"type": "array", "items": {"type": "string"}},
        "statistical_values": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "location": _NULLABLE_STRING,
                },
                "required": ["name", "value", "location"],
            },
        },
        "outliers": {"type": "array", "items": {"type": "string"}},
        "r_output": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "code": {"type": "array", "items": {"type": "string"}},
                "results": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "errors": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["code", "results", "warnings", "errors"],
        },
        "quality_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["blurry", "cropped_axis", "missing_label",
                                 "unreadable_value", "low_resolution", "other"],
                    },
                    "description": {"type": "string"},
                },
                "required": ["type", "description"],
            },
        },
        "unreadable_elements": {"type": "array", "items": {"type": "string"}},
        "overall_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "summary": {"type": "string"},
    },
    "required": [
        "content_type", "chart_type", "title", "axes", "legend", "variables",
        "trends", "statistical_values", "outliers", "r_output",
        "quality_issues", "unreadable_elements", "overall_confidence", "summary",
    ],
}

SYSTEM_PROMPT = """You are the evidence extractor for an introductory data science course.
You receive an image of a student's chart, graph, or R console output. Record ONLY what is
actually visible. Another component will later compare the student's interpretation to your
evidence, so accuracy matters more than completeness.

Rules:
- Never invent or estimate a title, label, unit, legend entry, or number that you cannot read.
  Use null (or an empty list) for anything not shown, and add it to unreadable_elements or
  quality_issues when it is present but illegible.
- Only record text you can read with certainty, character by character. If any character of
  a label or number is uncertain (small, blurry, or pixelated text), do NOT record a best
  guess: set the field to null, leave the value out of statistical_values, and describe it
  in unreadable_elements (e.g. "correlation annotation in upper left, digits illegible").
- Never infer a label, unit, or variable name from the title, the chart type, or what
  would be typical. An axis label you cannot read is null even if the title suggests one.
- Do not mention annotations, text, or values that are not visible in the image.
- Copy statistical values exactly as printed (e.g. "r = 0.82", "p-value: < 2.2e-16").
  Do not compute new statistics. Approximate readings from a plot are allowed only in trends
  or outliers and must be marked as approximate (e.g. "peak near x = 40 (approximate)").
- Describe trends, patterns, and relationships in plain language, including direction,
  strength, shape (skew, modality, spread), and clusters where visible.
- For a confusion matrix, record class labels as axes/variables and each cell count in
  statistical_values (name like "actual=yes, predicted=no").
- For R output, separate the code lines, printed results, warnings, and errors.
- Report quality problems: blurry or low-resolution images, cropped axes, missing axis labels
  or titles, and values that cannot be read. If the image is too unclear to analyze, set
  content_type to "unreadable" and overall_confidence to "low".
- overall_confidence reflects how reliably the visible content could be read.
- summary: 2-4 neutral sentences describing what the file shows. Do not evaluate any student.
"""


def get_openai_api_key() -> str | None:
    """Return the OpenAI API key from the environment or Streamlit secrets.

    Input:  none.
    Output: the key string, or None if it is not configured.
    """
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("OPENAI_API_KEY")
    except Exception:  # No secrets file, or not running under Streamlit.
        return None


def get_model_name() -> str:
    """Return the vision model name (OPENAI_MODEL env/secret, else DEFAULT_MODEL)."""
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        try:
            import streamlit as st
            model = st.secrets.get("OPENAI_MODEL")
        except Exception:
            model = None
    return model or DEFAULT_MODEL


def load_pages(file_bytes: bytes, filename: str, mime_type: str | None = None):
    """Convert an uploaded file into a list of page images.

    Input:
        file_bytes: raw bytes of the upload (e.g. uploaded_file.getvalue()).
        filename:   original file name; its extension decides the file type.
        mime_type:  optional MIME type from Streamlit (uploaded_file.type).
    Output:
        (pages, file_kind, pdf_text)
        pages:     list of RGB PIL.Image objects (one per image / PDF page).
        file_kind: "image" or "pdf".
        pdf_text:  embedded text from the PDF, or None for images / scanned PDFs.
    Raises:
        ValueError for unsupported, empty, or corrupt files.
    """
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported file type. Upload a PNG, JPG, JPEG, or PDF file.")
    if not file_bytes:
        raise ValueError("The uploaded file is empty.")

    if extension == "pdf" or mime_type == "application/pdf":
        import pymupdf  # PyMuPDF renders PDF pages to images.

        try:
            document = pymupdf.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError("The PDF could not be opened. It may be corrupt.") from exc
        pages, texts = [], []
        with document:
            if document.page_count == 0:
                raise ValueError("The PDF has no pages.")
            for page in list(document)[:MAX_PDF_PAGES]:
                texts.append(page.get_text().strip())
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(PDF_RENDER_ZOOM, PDF_RENDER_ZOOM))
                pages.append(Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB"))
        pdf_text = "\n\n".join(t for t in texts if t) or None
        return pages, "pdf", pdf_text

    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image)  # Respect phone-photo rotation.
        return [image.convert("RGB")], "image", None
    except Exception as exc:
        raise ValueError("The image could not be opened. It may be corrupt.") from exc


def check_image_quality(image: Image.Image) -> dict:
    """Run quick local checks for low resolution and blur (no API call).

    Input:  an RGB PIL image.
    Output: {"width", "height", "sharpness_score", "flags"} where flags may
            contain "low_resolution" and/or "possibly_blurry".

    The sharpness score is the variance of an edge-detection filter on the
    grayscale image. Crisp chart text and lines give high variance; blurred
    images give low variance. It is a hint passed to the model, which makes
    the final call on readability.
    """
    width, height = image.size
    flags = []
    if min(width, height) < MIN_READABLE_SIDE:
        flags.append("low_resolution")

    gray = image.convert("L")
    gray.thumbnail((1024, 1024))  # Normalize scale so scores are comparable.
    edges = gray.filter(ImageFilter.FIND_EDGES)
    sharpness = ImageStat.Stat(edges).var[0]
    if sharpness < BLUR_THRESHOLD:
        flags.append("possibly_blurry")

    return {"width": width, "height": height,
            "sharpness_score": round(sharpness, 1), "flags": flags}


def _image_to_data_url(image: Image.Image) -> str:
    """Downscale if needed and encode an image as a base64 PNG data URL."""
    image = image.copy()
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def build_messages(pages, quality_checks, pdf_text=None) -> list:
    """Build the chat messages sent to the multimodal model.

    Input:  page images, their local quality checks, and optional PDF text.
    Output: a list of chat messages (system prompt + one user message that
            contains context text and every page image).
    """
    context = [f"Pages provided: {len(pages)}."]
    for i, check in enumerate(quality_checks, start=1):
        context.append(
            f"Page {i}: {check['width']}x{check['height']} px; "
            f"automatic quality flags: {', '.join(check['flags']) or 'none'}."
        )
        if check["flags"]:
            context.append(
                f"Page {i} was flagged as degraded. Small text and numbers on it are likely "
                "illegible: record them as unreadable unless every character is clear."
            )
    if pdf_text:
        # The text layer gives exact characters for R output saved as PDF.
        context.append("Text embedded in the PDF (use it to read values exactly):\n"
                       + pdf_text[:6000])
    context.append("Extract the evidence according to the schema.")

    content = [{"type": "text", "text": "\n".join(context)}]
    for page in pages:
        content.append({"type": "image_url",
                        "image_url": {"url": _image_to_data_url(page), "detail": "high"}})
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}]


def _error_result(message: str, filename: str, model: str) -> dict:
    return {"status": "error", "error": message,
            "source": {"filename": filename, "file_kind": None,
                       "pages_analyzed": 0, "pdf_text": None},
            "local_quality_checks": [], "evidence": None, "model": model}


def analyze_evidence(file_bytes: bytes, filename: str, mime_type: str | None = None,
                     client=None, model: str | None = None) -> dict:
    """Analyze an uploaded chart / graph / R output and return structured evidence.

    Input:
        file_bytes: raw bytes of the upload (uploaded_file.getvalue()).
        filename:   original file name (uploaded_file.name).
        mime_type:  optional MIME type (uploaded_file.type).
        client:     optional OpenAI client (used by tests); created from the
                    configured API key when omitted.
        model:      optional model override; defaults to get_model_name().
    Output:
        The evidence dictionary described in EVIDENCE CONTRACT above.
        Bad files, a missing API key, and API failures are returned as
        status "error" with a message instead of raising.
    """
    model = model or get_model_name()

    try:
        pages, file_kind, pdf_text = load_pages(file_bytes, filename, mime_type)
    except ValueError as exc:
        return _error_result(str(exc), filename, model)

    quality_checks = [{"page": i, **check_image_quality(page)}
                      for i, page in enumerate(pages, start=1)]
    result = {
        "status": "ok", "error": None,
        "source": {"filename": filename, "file_kind": file_kind,
                   "pages_analyzed": len(pages), "pdf_text": pdf_text},
        "local_quality_checks": quality_checks,
        "evidence": None, "model": model,
    }

    if client is None:
        api_key = get_openai_api_key()
        if not api_key:
            return _error_result(
                "OpenAI API key not configured. Set OPENAI_API_KEY in Streamlit "
                "secrets or as an environment variable.", filename, model)
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=build_messages(pages, quality_checks, pdf_text),
            response_format={"type": "json_schema",
                             "json_schema": {"name": "chart_evidence", "strict": True,
                                             "schema": EVIDENCE_SCHEMA}},
            max_completion_tokens=8000,
        )
    except Exception as exc:  # Network, auth, rate limit, or model errors.
        return _error_result(f"OpenAI request failed: {exc}", filename, model)

    message = response.choices[0].message
    if getattr(message, "refusal", None):
        return _error_result(f"The model declined to analyze this file: {message.refusal}",
                             filename, model)
    try:
        result["evidence"] = json.loads(message.content)
    except (TypeError, json.JSONDecodeError):
        return _error_result("The model returned an incomplete response. Please try again.",
                             filename, model)
    apply_quality_safeguards(result["evidence"], quality_checks)
    return result


def _withhold_text_readings(evidence: dict) -> None:
    """Move text read from a blurry file out of the evidence (see apply_quality_safeguards)."""
    unverified = evidence["unreadable_elements"]
    if evidence["title"]:
        unverified.append(f"title: possibly '{evidence['title']}' (unverified, image blurry)")
        evidence["title"] = None
    for axis in evidence["axes"]:
        for field in ("label", "units", "range"):
            if axis[field]:
                unverified.append(f"{axis['axis']}-axis {field}: possibly '{axis[field]}' "
                                  "(unverified, image blurry)")
                axis[field] = None
    for stat in evidence["statistical_values"]:
        unverified.append(f"{stat['name']}: possibly '{stat['value']}' (unverified, image blurry)")
    evidence["statistical_values"] = []
    evidence["summary"] = ("The image is blurry, so any title, labels, or numbers mentioned here "
                           "could not be verified. " + evidence["summary"])


_PLACEHOLDER_VALUES = {"", "illegible", "unreadable", "unknown", "not readable", "n/a", "?"}


def apply_quality_safeguards(evidence: dict, quality_checks: list) -> dict:
    """Apply code-level checks that do not rely on the model following its prompt.

    Input:  the model's evidence dict and the local quality checks.
    Output: the same evidence dict, modified in place and returned:
        - statistical_values whose value is a placeholder such as "illegible"
          are moved to unreadable_elements.
        - if any page was flagged "possibly_blurry" or "low_resolution",
          overall_confidence is set to "low" and a quality issue is added,
          because live testing showed the model can still guess labels and
          values on blurred or very small images.
        - if any page was flagged "possibly_blurry", text the model read from
          the file (title, axis labels/units/ranges, statistical values) is
          moved to unreadable_elements marked "unverified", so it is never
          treated as evidence, and the summary starts with a note that names
          and numbers in it are unverified. Visual trends and outliers are
          kept. Evidence is not split by page, so this applies to the whole file.
    """
    kept = []
    for stat in evidence["statistical_values"]:
        if stat["value"].strip().strip("<>").strip().lower() in _PLACEHOLDER_VALUES:
            evidence["unreadable_elements"].append(f"{stat['name']} (value illegible)")
        else:
            kept.append(stat)
    evidence["statistical_values"] = kept

    if any("possibly_blurry" in c["flags"] for c in quality_checks):
        _withhold_text_readings(evidence)

    for flag, issue_type, wording in [("possibly_blurry", "blurry", "blurry"),
                                      ("low_resolution", "low_resolution", "very low resolution")]:
        pages = [str(c["page"]) for c in quality_checks if flag in c["flags"]]
        if pages:
            evidence["overall_confidence"] = "low"
            evidence["quality_issues"].append({
                "type": issue_type,
                "description": f"Automatic check found page(s) {', '.join(pages)} {wording}. "
                               "Labels and values read from this file may be inaccurate; "
                               "upload a clearer, larger image.",
            })
    return evidence


def evidence_to_text(result: dict) -> str:
    """Render an evidence result as compact plain text.

    Input:  the dictionary returned by analyze_evidence.
    Output: a readable multi-line string. Latonya can paste this into her
            evaluation prompt instead of raw JSON if she prefers.
    """
    if result.get("status") != "ok" or not result.get("evidence"):
        return f"Evidence unavailable: {result.get('error')}"
    ev = result["evidence"]
    lines = [f"Content type: {ev['content_type']}",
             f"Chart type: {ev['chart_type'] or 'not identified'}",
             f"Title: {ev['title'] or 'none visible'}"]
    for axis in ev["axes"]:
        lines.append(f"Axis {axis['axis']}: label={axis['label']}, units={axis['units']}, "
                     f"scale={axis['scale']}, range={axis['range']}")
    sections = [
        ("Legend", [f"{x['label']}: {x['meaning']}" for x in ev["legend"]]),
        ("Variables", ev["variables"]),
        ("Trends", ev["trends"]),
        ("Statistical values", [f"{s['name']} = {s['value']}" for s in ev["statistical_values"]]),
        ("Outliers", ev["outliers"]),
        ("R code", ev["r_output"]["code"]),
        ("R results", ev["r_output"]["results"]),
        ("R warnings", ev["r_output"]["warnings"]),
        ("R errors", ev["r_output"]["errors"]),
        ("Quality issues", [f"{q['type']}: {q['description']}" for q in ev["quality_issues"]]),
        ("Unreadable elements", ev["unreadable_elements"]),
    ]
    for heading, items in sections:
        if items:
            lines.append(f"{heading}:")
            lines.extend(f"  - {item}" for item in items)
    lines.append(f"Confidence: {ev['overall_confidence']}")
    lines.append(f"Summary: {ev['summary']}")
    return "\n".join(lines)


# =============================================================================
# PART 2 - INTERPRETATION EVALUATION (Latonya Smith)
# =============================================================================
#
# Not implemented here; this section is reserved for Latonya.
#
# How to consume the evidence:
#   result = analyze_evidence(file.getvalue(), file.name, file.type)
#   if result["status"] != "ok": show result["error"] and stop.
#   ev = result["evidence"]
#
#   - Compare claims in the student's interpretation against ev["trends"],
#     ev["statistical_values"], ev["outliers"], and ev["axes"] (labels/units).
#   - Treat anything in ev["unreadable_elements"] or ev["quality_issues"] as
#     unverifiable: do not mark a student claim wrong if it depends on a value
#     the evidence could not read; flag it as "cannot be verified" instead.
#   - Lower the certainty of feedback when ev["overall_confidence"] == "low"
#     or result["local_quality_checks"] contains flags.
#   - For R output, check that the student does not ignore ev["r_output"]
#     ["warnings"] / ["errors"].
#   - evidence_to_text(result) gives a prompt-ready text version.
#
# Integration point in app.py: the "Submit for review" handler on the
# Review Agent page stores the result in st.session_state["review_evidence"];
# call your evaluation function there with that result, the interpretation
# text, and the assignment type.
