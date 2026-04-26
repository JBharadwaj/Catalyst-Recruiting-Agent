import streamlit as st
import json
import os
import requests
from groq import Groq
from ranking_agent import calculate_python_scores

# ---------------- CONFIG ----------------
os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

RESULTS_FILE = "final_recruiter_data.json"
CANDIDATES_API = "https://catalyst-recruiting-agent-1.onrender.com/get_candidates"
JD_API = "https://catalyst-recruiting-agent-1.onrender.com/get_job_descriptions"
#CANDIDATES_API = st.secrets["CANDIDATES_API"]
#JD_API = st.secrets["JD_API"]


def get_top_candidates():
    try:
        cands_resp = requests.get(CANDIDATES_API).json()
        jds_resp = requests.get(JD_API).json()
        
        cands = cands_resp.get("candidates", {})
        jds = jds_resp.get("job_descriptions", {})

        # --- FIX 1: CHECK IF JDS EXIST ---
        if not jds:
            st.error("Error: No job descriptions found in JD_API.")
            return [], None, None
            
        jd_keys = list(jds.keys())
        if not jd_keys:
            st.error("Error: Job description list is empty.")
            return [], None, None
            
        jd_title = jd_keys[0]
        jd_info = jds[jd_title]

        if not cands:
            st.warning("No candidates found in API.")
            return [], jd_title, jd_info

        scored_candidates = []
        for name, profile in cands.items():
            # Safety check: ensure profile and jd_info are valid for the ranker
            try:
                score, _, _ = calculate_python_scores(profile, jd_info)
                scored_candidates.append((name, profile, score))
            except Exception as e:
                print(f"Skipping {name} due to scoring error: {e}")

        scored_candidates.sort(key=lambda x: x[2], reverse=True)
        return scored_candidates[:2], jd_title, jd_info

    except Exception as e:
        st.error(f"Actual Error: {str(e)}") 
        return [], None, None

# ---------------- UI INITIALIZATION ----------------
st.title("🤝 Catalyst Recruiting Agent")

# Consolidated initialization block
if "top_candidates" not in st.session_state:
    with st.spinner("Fetching initial data..."):
        cands, title, info = get_top_candidates()
        
        # We only set these if we actually got candidates
        if cands:
            st.session_state.top_candidates = cands
            st.session_state.jd_title = title
            st.session_state.jd_info = info
            st.session_state.current_candidate_index = 0
            st.session_state.messages = []
            st.session_state.questions_asked = 0
            st.session_state.chat_complete = False
        else:
            # If API failed or returned 0, we show a button to try again
            st.error("Could not load candidates. The API might be down or returning empty data.")
            if st.button("🔄 Retry Connection"):
                st.rerun()
            st.stop() # Prevents the rest of the app from running with empty data# ---------------- SAVE RESULTS ----------------
def save_to_file(name, match_score, interest_score, note):
    new_entry = {
        "candidate_name": name,
        "match_score": match_score,
        "interest_score": interest_score,
        "recruiter_note": note,
        "final_average": (match_score + interest_score) / 2
    }

    data = []
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r") as f:
            data = json.load(f)

    data.append(new_entry)

    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ---------------- AI DISINTEREST CHECK ----------------
def detect_disinterest_ai(chat_history, latest_message):
    prompt = f"""
Analyze if the candidate is NOT interested in the job.

Conversation:
{chat_history}

Latest message:
"{latest_message}"

Rules:
- Rejecting / avoiding → TRUE
- Neutral → FALSE
- Interested → FALSE

Return JSON:
{{
    "disinterested": true/false,
    "reason": "short reason"
}}
"""

    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    return json.loads(completion.choices[0].message.content)


# ---------------- AI INTEREST ANALYSIS ----------------
def analyze_interest_ai(chat_history):
    prompt = f"""
Analyze this recruiter-candidate conversation.

Return JSON:
- score (0-100)
- note

Chat:
{chat_history}
"""

    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    return json.loads(completion.choices[0].message.content)


# ---------------- AI RECRUITER ----------------
def recruiter_chat_ai(messages, jd_title, jd_info, candidate_profile, question_count):
    prompt = f"""
You are a HUMAN HR RECRUITER.

Role: {jd_title}
JD: {jd_info}
Candidate: {candidate_profile}

Conversation:
{messages}

Rules:
- Be conversational
- Ask 1 question at a time
- Max 10 questions
- Focus on interest, availability, salary, goals
- No deep tech

Adapt:
- Disinterest → be polite
- Interest → move faster

Return ONLY next message.
"""

    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )

    return completion.choices[0].message.content




# Initialize session
if "initialized" not in st.session_state:
    st.session_state.top_candidates, st.session_state.jd_title, st.session_state.jd_info = get_top_candidates()
    st.session_state.current_candidate_index = 0
    st.session_state.messages = []
    st.session_state.questions_asked = 0
    st.session_state.chat_complete = False
    st.session_state.initialized = True


# ---------------- PROCESS CANDIDATES ----------------
if st.session_state.current_candidate_index < len(st.session_state.top_candidates):

    name, profile, match_score = st.session_state.top_candidates[st.session_state.current_candidate_index]

    st.subheader(f"👤 Candidate: {name}")

    # Initial message
    if len(st.session_state.messages) == 0:
        first_msg = recruiter_chat_ai(
            [],
            st.session_state.jd_title,
            st.session_state.jd_info,
            profile,
            0
        )
        st.session_state.messages.append({"role": "assistant", "content": first_msg})

    # Display chat
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ---------------- CHAT FLOW ----------------
    if not st.session_state.chat_complete:
        if user_input := st.chat_input("Reply to recruiter..."):

            st.session_state.messages.append({"role": "user", "content": user_input})

            with st.chat_message("user"):
                st.markdown(user_input)

            # 🔴 CHECK DISINTEREST
            result = detect_disinterest_ai(
                st.session_state.messages[-6:],
                user_input
            )

            if result["disinterested"]:
                exit_msg = "Thanks for your time. We understand you're not interested right now. We'll reach out in future opportunities."

                st.session_state.messages.append({"role": "assistant", "content": exit_msg})

                with st.chat_message("assistant"):
                    st.markdown(exit_msg)

                save_to_file(name, match_score, 0, result["reason"])

                st.warning("❌ Candidate not interested")

                st.session_state.chat_complete = True
                st.rerun()

            # ✅ CONTINUE
            st.session_state.questions_asked += 1

            ai_reply = recruiter_chat_ai(
                st.session_state.messages[-6:],
                st.session_state.jd_title,
                st.session_state.jd_info,
                profile,
                st.session_state.questions_asked
            )

            st.session_state.messages.append({"role": "assistant", "content": ai_reply})

            with st.chat_message("assistant"):
                st.markdown(ai_reply)

            if st.session_state.questions_asked >= 10:
                st.session_state.chat_complete = True

    # ---------------- FINAL ANALYSIS ----------------
    if st.session_state.chat_complete:
        with st.spinner("Analyzing..."):

            interest_data = analyze_interest_ai(str(st.session_state.messages[-8:]))

            save_to_file(
                name,
                match_score,
                interest_data["score"],
                interest_data["note"]
            )

            total = (match_score + interest_data["score"]) / 2

            if total >= 70:
                st.success("✅ Move to interview")
            else:
                st.error("❌ Not shortlisted")

        if st.button("➡️ Next Candidate"):
            st.session_state.current_candidate_index += 1
            st.session_state.messages = []
            st.session_state.questions_asked = 0
            st.session_state.chat_complete = False
            st.rerun()

else:
    st.balloons()
    st.success("🎉 All candidates processed!")

    if st.button("🔄 Restart Cycle"):
        # Clear everything related to the current run
        for key in ["top_candidates", "current_candidate_index", "messages", "questions_asked", "chat_complete"]:
            if key in st.session_state:
                del st.session_state[key]
        
        # This force-clears the cache and triggers the Init block at the top
        st.rerun()