# LearnDataAI

Evidence checking learning assistant for Introduction to Data Science. Existing Streamlit UI by Mera Singh; backend implementation is assigned below.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

| File | Owner | Due |
| --- | --- | --- |
| app.py | Mera Singh | Nov 30 |
| r_workspace.py | Corinthian Ewesuedo | Nov 30 |
| review_agent.py | Mack Jackson and Latonya Smith | Dec 1 |
| coaching_agent.py | Lakeitha Beal | Dec 1 |
| media.py | Jamie Sterling | Dec 2 |
| course_materials.py | Shared coordination | Dec 2 |
| tests/README.md | All members | Dec 4 |

## OpenAI API key (Review Agent)

Locally, create `.streamlit/secrets.toml` (already in `.gitignore`):

```toml
OPENAI_API_KEY = "your-key"
# OPENAI_MODEL = "gpt-5.4-mini"   # optional override
```

On Streamlit Community Cloud, add the same lines under the app's **Settings → Secrets**. An `OPENAI_API_KEY` environment variable also works.

Final integration and presentation: December 6. Keep API keys in Streamlit secrets or environment variables, never in Git. The UI is runnable. In review_agent.py, evidence analysis (Mack Jackson) is implemented and connected to the Review Agent page; interpretation evaluation (Latonya Smith) and the other backend modules are still placeholders.
