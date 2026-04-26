import streamlit as st
import json
import os
import requests
import uuid
from groq import Groq
from ranking_agent import calculate_python_scores

# ---------------- CONFIG ----------------
os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

CANDIDATES_API = st.secrets["CANDIDATES_API"]
JD_API = st.secrets["JD_API"]

# ---------------- FETCH TOP CANDIDATES ----------------
def get_top_candidates():
    try:
        cands = requests.get(CANDIDATES_API, headers={"Cache-Control": "no-cache"}).json().get("candidates", {})
        jds = requests.get(JD_API, headers={"Cache-Control": "no-cache"}).json().get("job_descriptions", {})

        jd_title = list(jds.keys())[0]
        jd_info = jds[jd_title]

        scored_candidates = []

        for name, profile in cands.items():
            score, _, _ = calculate_python_scores(profile, jd_info)
            scored_candidates.append((name, profile, score))

        scored_candidates.sort(key=lambda x: x[2], reverse=True)

        return scored_candidates[:2], jd_title, jd_info

    except Exception as e:
        print(f"Error fetching candidates: {e}")
        return [], None, None


# ---------------- SAVE RESULTS ----------------
def save_to_file(name, match_score, interest_score, note):
    if "file_id" not in st.session_state:
        st.session_state.file_id = str(uuid.uuid4())

    RESULTS_FILE = f"results_{st.session_state.file_id}.json"

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


# ---------------- AI FUNCTIONS ----------------
def detect_disinterest_ai(chat_history, latest_message):
    prompt = f"""
Analyze if the candidate is NOT interested.

Conversation:
{chat_history}

Latest:
"{latest_message}"

Return JSON:
{{"disinterested": true/false, "reason": "short"}}
"""

    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    return json.loads(res.choices[0].message.content)


def analyze_interest_ai(chat_history):
    prompt = f"""
Analyze conversation.

Return JSON:
{{"score":0-100, "note":"short"}}

Chat:
{chat_history}
"""

    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    return json.loads(res.choices[0].message.content)


def recruiter_chat_ai(messages, jd_title, jd_info, profile):
    prompt = f"""
You are a HR recruiter.

Role: {jd_title}
JD: {jd_info}
Candidate: {profile}

Chat:
{messages}

Rules:
- Ask 1 question
- Max 10 total
- Keep short
"""

    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )

    return res.choices[0].message.content


# ---------------- INIT SESSION ----------------
def init_session():
    top, jd_title, jd_info = get_top_candidates()
    st.session_state.top_candidates = top
    st.session_state.jd_title = jd_title
    st.session_state.jd_info = jd_info
    st.session_state.current_candidate_index = 0
    st.session_state.messages = []
    st.session_state.questions_asked = 0
    st.session_state.chat_complete = False


if "current_candidate_index" not in st.session_state:
    init_session()


# ---------------- UI ----------------
st.title("🤝 Catalyst Recruiting Agent")

if st.button("🔄 Restart"):
    st.session_state.clear()
    st.rerun()


# ---------------- MAIN FLOW ----------------
if st.session_state.current_candidate_index < len(st.session_state.top_candidates):

    name, profile, match_score = st.session_state.top_candidates[st.session_state.current_candidate_index]

    st.subheader(f"👤 Candidate: {name}")

    if len(st.session_state.messages) == 0:
        msg = recruiter_chat_ai([], st.session_state.jd_title, st.session_state.jd_info, profile)
        st.session_state.messages.append({"role": "assistant", "content": msg})

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if not st.session_state.chat_complete:
        if user_input := st.chat_input("Reply..."):

            st.session_state.messages.append({"role": "user", "content": user_input})

            with st.chat_message("user"):
                st.markdown(user_input)

            result = detect_disinterest_ai(st.session_state.messages[-6:], user_input)

            if result["disinterested"]:
                st.warning("❌ Not interested")
                save_to_file(name, match_score, 0, result["reason"])
                st.session_state.chat_complete = True
                st.rerun()

            st.session_state.questions_asked += 1

            reply = recruiter_chat_ai(
                st.session_state.messages[-6:],
                st.session_state.jd_title,
                st.session_state.jd_info,
                profile
            )

            st.session_state.messages.append({"role": "assistant", "content": reply})

            with st.chat_message("assistant"):
                st.markdown(reply)

            if st.session_state.questions_asked >= 10:
                st.session_state.chat_complete = True

    if st.session_state.chat_complete:
        data = analyze_interest_ai(str(st.session_state.messages[-8:]))

        save_to_file(name, match_score, data["score"], data["note"])

        total = (match_score + data["score"]) / 2

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


# ---------------- AUTO RESTART ----------------
else:
    st.success("🎉 All candidates processed! Restarting...")

    # Show a brief summary or message before the hard reset
    if st.button("🚀 Start New Batch"):
        # This is the cleanest way to "factory reset" the app
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()