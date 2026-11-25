import hashlib

import streamlit as st

from review_agent import analyze_evidence, evidence_to_text

# UI owner: Mera Singh. Backend integration points are marked below.

st.set_page_config(page_title="LearnDataAI", layout="wide")

# Minimal styling: dark interface, simple typography, square controls.
st.markdown("""
<style>
.stApp {background: #0d1117; color: #e6edf3;}
[data-testid="stSidebar"] {background: #151b23; border-right: 1px solid #30363d;}
h1, h2, h3 {letter-spacing: -0.035em; font-weight: 600;}
h1 {font-size: 2.2rem !important;}
[data-testid="stMetric"] {background: #151b23; border: 1px solid #30363d; padding: 16px;}
.stButton > button {border-radius: 4px; background: #2563eb; color: white; border: none;}
.stButton > button:hover {background: #1d4ed8; color: white;}
[data-testid="stFileUploader"], textarea, input {border-radius: 4px !important;}
hr {border-color: #30363d;}
.small-label {color: #8b949e; font-size: 0.82rem; letter-spacing: .08em; text-transform: uppercase;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("LearnDataAI")
    st.caption("DATA SCIENCE LEARNING PLATFORM")
    st.divider()
    page = st.radio(
        "Workspace",
        ["Overview", "Review Agent", "Coaching Agent", "R Workspace", "Course Materials"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("PROTOTYPE  /  UI ONLY")

if page == "Overview":
    st.markdown('<p class="small-label">Workspace / Overview</p>', unsafe_allow_html=True)
    st.title("Understand your data.")
    st.write("Review visualizations, practice interpretations, and work through R concepts in one place.")
    st.divider()
    a, b, c = st.columns(3)
    a.metric("Agents", "02")
    b.metric("Workspace", "R")
    c.metric("Status", "Prototype")
    st.subheader("Start here")
    st.write("**Review Agent** — Submit a chart and your interpretation for evidence-based review.")
    st.write("**Coaching Agent** — Ask questions and receive guided hints.")
    st.write("**R Workspace** — Write R code and view results after backend integration.")

# Mack Jackson and Latonya Smith: connect review_agent.py here.
elif page == "Review Agent":
    st.markdown('<p class="small-label">Workspace / Review</p>', unsafe_allow_html=True)
    st.title("Review Agent")
    st.caption("Submit a chart or R output and explain what you think it shows.")
    left, right = st.columns([1, 1], gap="large")
    with left:
        file = st.file_uploader("Chart or R output", type=["png", "jpg", "jpeg", "pdf"])
        if file and file.type.startswith("image/"):
            st.image(file, caption=file.name, use_container_width=True)
        elif file:
            st.caption(f"Selected: {file.name}")
    with right:
        assignment = st.selectbox("Assignment type", ["Practice", "Graded work"])
        interpretation = st.text_area("Your interpretation", height=190,
                                      placeholder="Describe the pattern, labels, and evidence...")
        if st.button("Submit for review", use_container_width=True):
            if not file or not interpretation.strip():
                st.warning("Add a chart and an interpretation first.")
            else:
                # Mack: evidence analysis. Reuse the result if the same file is resubmitted.
                file_bytes = file.getvalue()
                file_key = hashlib.sha256(file_bytes).hexdigest()
                cached = st.session_state.get("review_evidence")
                if not cached or cached.get("file_key") != file_key or cached["status"] != "ok":
                    with st.spinner("Analyzing chart evidence..."):
                        cached = analyze_evidence(file_bytes, file.name, file.type)
                        cached["file_key"] = file_key
                    st.session_state["review_evidence"] = cached
                # Latonya: call the interpretation evaluation here with
                # st.session_state["review_evidence"], interpretation, and assignment.
                if cached["status"] == "ok":
                    st.info("Evidence extracted. Interpretation feedback will appear once evaluation is connected.")

    # Mack: show the extracted evidence for the current upload.
    result = st.session_state.get("review_evidence")
    if file and result and result.get("file_key") == hashlib.sha256(file.getvalue()).hexdigest():
        st.divider()
        st.subheader("Evidence")
        if result["status"] != "ok":
            st.error(result["error"])
        else:
            ev = result["evidence"]
            m1, m2, m3 = st.columns(3)
            m1.metric("Content", ev["content_type"].replace("_", " ").title())
            m2.metric("Chart type", (ev["chart_type"] or "None").title())
            m3.metric("Confidence", ev["overall_confidence"].title())
            st.write(ev["summary"])
            issues = [f"**{q['type'].replace('_', ' ')}**: {q['description']}" for q in ev["quality_issues"]]
            issues += [f"**unreadable**: {item}" for item in ev["unreadable_elements"]]
            if issues:
                st.warning("Some details could not be confirmed from the file:\n\n- " + "\n- ".join(issues))
            with st.expander("Extracted details"):
                st.code(evidence_to_text(result), language="text")
            with st.expander("Structured evidence (JSON)"):
                st.json({k: v for k, v in result.items() if k != "file_key"})

# Lakeitha Beal: connect coaching_agent.py here.
elif page == "Coaching Agent":
    st.markdown('<p class="small-label">Workspace / Coaching</p>', unsafe_allow_html=True)
    st.title("Coaching Agent")
    st.caption("Ask about charts, interpretations, and introductory data science concepts.")
    question = st.text_area("Your question", placeholder="What does this scatterplot suggest?", height=130)
    mode = st.selectbox("Response format", ["Guided hint", "Written explanation", "Practice question"])
    if st.button("Ask coach"):
        if question.strip():
            st.info("Question captured. Connect the Coaching Agent to generate a response.")
        else:
            st.warning("Enter a question first.")

# Corinthian Ewesuedo: connect r_workspace.py here.
elif page == "R Workspace":
    st.markdown('<p class="small-label">Workspace / R</p>', unsafe_allow_html=True)
    st.title("R Workspace")
    st.caption("Write R code here. Execution will be added by the coding-workspace developer.")
    code = st.text_area("Editor", value="data <- c(4, 7, 9, 12)\nmean(data)", height=280)
    if st.button("Run code"):
        st.info("R execution is not connected yet. The code editor is ready for integration.")
    st.subheader("Output")
    st.code("Output will appear here after backend integration.", language="text")

# Team: coordinate course retrieval. Jamie Sterling: connect media.py to agent pages.
elif page == "Course Materials":
    st.markdown('<p class="small-label">Workspace / Resources</p>', unsafe_allow_html=True)
    st.title("Course Materials")
    st.caption("Select instructor resources or personal notes for later knowledge-base integration.")
    source = st.radio("Material type", ["Instructor materials", "Personal notes"], horizontal=True)
    files = st.file_uploader("Upload materials", type=["pdf", "txt", "docx", "pptx", "png", "jpg"],
                             accept_multiple_files=True)
    if files:
        st.write("Selected files:")
        for item in files:
            st.write(f"- {item.name}")
        st.info("Files are selected in this session only; ChromaDB storage is not connected yet.")
