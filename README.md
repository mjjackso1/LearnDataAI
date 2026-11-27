# LearnDataAI

Evidence checking learning assistant for Introduction to Data Science. Existing Streamlit UI by Mera Singh; backend implementation is assigned below.

Live app: https://learndataai.streamlit.app

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The Review Agent needs an OpenAI API key (see below). The other pages run without one.

## Team and status

| File | Owner | Due | Status |
| --- | --- | --- | --- |
| app.py | Mera Singh | Nov 30 | UI complete; Review Agent connected |
| r_workspace.py | Corinthian Ewesuedo | Nov 30 | Placeholder |
| review_agent.py | Mack Jackson and Latonya Smith | Dec 1 | Evidence analysis and interpretation evaluation implemented |
| coaching_agent.py | Lakeitha Beal | Dec 1 | Placeholder |
| media.py | Jamie Sterling | Dec 2 | Placeholder |
| course_materials.py | Shared coordination | Dec 2 | Placeholder |
| tests/README.md | All members | Dec 4 | Not started |

## OpenAI API key

Locally, create `.streamlit/secrets.toml` (already in `.gitignore`):

```toml
OPENAI_API_KEY = "your-key"
# OPENAI_MODEL = "gpt-5.4-mini"   # optional override
```

On Streamlit Community Cloud, add the same lines under the app's **Settings → Secrets**. An `OPENAI_API_KEY` environment variable also works. Keep API keys in Streamlit secrets or environment variables, never in Git.

## Review Agent

The student uploads a chart or R output (PNG, JPG, JPEG, or PDF), writes an interpretation, and selects **Submit for review**. `review_agent.py` handles it in two steps.

**1. Evidence analysis**: `analyze_evidence(file_bytes, filename, mime_type)`

- Sends the file to the OpenAI multimodal API and returns structured evidence: chart type, title, axes (label, units, scale, range), legend, variables, trends, statistical values, outliers, and R code, results, warnings, and errors.
- PDFs: the first 5 pages are converted to images, and any embedded text is passed along so R output is read exactly.
- Records only what is visible. Missing or illegible details are listed as unreadable rather than guessed.
- A local check flags blurry and very low-resolution images. Flagged files are marked low confidence, and on blurry files any text the model read is listed as unverified instead of being treated as evidence.
- The full output format is documented in the EVIDENCE CONTRACT comment in `review_agent.py`.

**2. Interpretation evaluation**: `evaluate_interpretation(result, interpretation, rubric, assignment_type)`

- Splits the interpretation into claims and labels each one supported, contradicted, cannot be verified, or not shown in the file.
- Lists misconceptions with corrections and important points the student missed, rates each rubric criterion, and writes feedback addressed to the student.
- Claims that depend on unreadable parts of the file are never marked wrong. Review confidence is never higher than the evidence confidence.
- Uses `DEFAULT_RUBRIC` until instructor rubrics come from Course Materials.

The page shows both results under **Evidence** and **Interpretation review**. Resubmitting the same file with a new interpretation reuses the evidence and only reruns the review.

**Known limitations**

- Very blurry or tiny images can't be read reliably. The app flags them and asks for a clearer upload.
- Model output varies between runs, and the review can occasionally misjudge a claim. Treat its feedback as guidance, not a grade.

## Schedule

Final integration and presentation: December 6.
