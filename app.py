import streamlit as st
import json
import os
import requests
import uuid
from groq import Groq
from ranking_agent import calculate_python_scores

# ---------------- 1. HARD RESET FUNCTION ----------------
def reset_entire_app():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ---------------- 2. CONFIG ----------------
os.environ["GROQ_API_KEY"] = st.secrets.get("GROQ_API_KEY", "")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
CANDIDATES_API = st.secrets.get("CANDIDATES_API", "")
JD_API = st.secrets.get("JD_API", "")

# ---------------- 3. FETCH & INIT ----------------
def get_top_candidates():
    try:
        cands = requests.get(CANDIDATES_API, headers={"Cache-Control": "no-cache"}).json().get("candidates", {})
        jds = requests.get(JD_API, headers={"Cache-Control": "no-cache"}).json().get("job_descriptions", {})
        
        if not jds or not cands: return [], None, None

        jd_title = list(jds.keys())[0]
        jd_info = jds[jd_title]
        scored_candidates = []

        for name, profile in cands.items():
            score, _, _ = calculate_python_scores(profile, jd_info)
            scored_candidates.append((name, profile, score))

        scored_candidates.sort(key=lambda x: x[2], reverse=True)
        return scored_candidates[:2], jd_title, jd_info
    except Exception as e:
        st.error(f"Fetch Error: {e}")
        return [], None, None

# This block only runs if the app was just started or just reset
if "top_candidates" not in st.session_state:
    top, title, info = get_top_candidates()
    st.session_state.top_candidates = top
    st.session_state.jd_title = title
    st.session_state.jd_info = info
    st.session_state.current_candidate_index = 0
    st.session_state.messages = []
    st.session_state.questions_asked = 0
    st.session_state.chat_complete = False
    st.session_state.file_id = str(uuid.uuid4())

# ---------------- 4. AI HELPERS ----------------
# (Keep your recruiter_chat_ai, analyze_interest_ai, etc. here)
# ... [Your AI functions from the previous block] ...

# ---------------- 5. UI & MAIN LOGIC ----------------
st.title("🤝 Catalyst Recruiting Agent")

# Sidebar reset is always good for testing
if st.sidebar.button("Force App Reset"):
    reset_entire_app()

# CHECK: Are we done with the list?
if st.session_state.current_candidate_index >= len(st.session_state.top_candidates):
    st.balloons()
    st.success("✅ All candidates processed!")
    
    # This button is the trigger to start over with "fresh" people
    if st.button("Start New Batch (Fresh Run)"):
        reset_entire_app()
    
    st.stop() # Prevents the rest of the code from running

# --- IF NOT DONE, RUN THE CHAT ---
name, profile, match_score = st.session_state.top_candidates[st.session_state.current_candidate_index]
st.subheader(f"Current Candidate: {name}")

# (Insert your Chat display and Input logic here)
# ... [Your Chat/Input logic from the previous block] ...

# --- THE NEXT CANDIDATE BUTTON ---
if st.session_state.chat_complete:
    # (Insert your evaluation/save logic here)
    
    if st.button("➡️ Next Candidate"):
        st.session_state.current_candidate_index += 1
        st.session_state.messages = []
        st.session_state.questions_asked = 0
        st.session_state.chat_complete = False
        st.rerun()