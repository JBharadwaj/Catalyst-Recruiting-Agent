
import streamlit as st
import json
import os
import requests
from groq import Groq
# Import the logic from your other file
from ranking_agent import calculate_python_scores 
from dotenv import load_dotenv
load_dotenv()
# 1. Configuration
import os
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

RESULTS_FILE = "final_recruiter_data.json"
CANDIDATES_API = "http://127.0.0.1:8000/get_candidates"
JD_API = "http://127.0.0.1:8000/get_job_descriptions"

# ---------------- FETCH TOP 2 CANDIDATES ----------------
def get_top_candidates():
    try:
        cands = requests.get(CANDIDATES_API).json().get("candidates", {})
        jds = requests.get(JD_API).json().get("job_descriptions", {})

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


# ---------------- AI INTEREST ANALYSIS ----------------
def analyze_interest_ai(chat_history):
    prompt = f"""
Analyze this recruiter-candidate conversation.

Return JSON:
- score (0-100): candidate interest level
- note: short reasoning

Chat:
{chat_history}
"""

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    return json.loads(completion.choices[0].message.content)


# ---------------- AI RECRUITER ----------------
def recruiter_chat_ai(messages, jd_title, jd_info, candidate_profile, question_count):
    prompt = f"""
You are a HUMAN-LIKE HR RECRUITER (not a technical interviewer).

Job Role: {jd_title}
Job Description: {jd_info}

Candidate Profile: {candidate_profile}

Conversation so far:
{messages}

Your Goal:
- Assess candidate INTEREST and INTENT, not deep technical skills

Rules:
- Start by clearly introducing the ROLE and COMPANY context
- Be warm, conversational, and professional
- Ask ONLY ONE question at a time
- Max 10 questions

Focus on:
1. Interest in this role
2. Reason for job change
3. Availability / notice period
4. Salary expectations
5. Career goals
6. Work preferences
7. Enthusiasm / seriousness

Avoid:
- Deep technical grilling
- Repeating questions
- Robotic behavior

Adapt:
- If candidate seems uninterested → try to re-engage
- If highly interested → move faster to closing

End:
- If enough info → conclude politely like a recruiter

Current question count: {question_count}

Return ONLY the next recruiter message.
"""

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )

    return completion.choices[0].message.content


# ---------------- STREAMLIT UI ----------------
st.title("🤝 Catalyst Recruiting agent")

# Initialize session
if "initialized" not in st.session_state:
    st.session_state.top_candidates, st.session_state.jd_title, st.session_state.jd_info = get_top_candidates()
    st.session_state.current_candidate_index = 0
    st.session_state.messages = []
    st.session_state.questions_asked = 0
    st.session_state.chat_complete = False
    st.session_state.initialized = True

# Get current candidate
if st.session_state.current_candidate_index < len(st.session_state.top_candidates):

    name, profile, match_score = st.session_state.top_candidates[st.session_state.current_candidate_index]

    st.subheader(f"👤 Candidate: {name}")
    st.write(f"📊 Match Score: {match_score}")

    # Initial AI message
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

    # Chat flow
    if not st.session_state.chat_complete:
        if user_input := st.chat_input("Reply to recruiter..."):
            st.session_state.messages.append({"role": "user", "content": user_input})

            with st.chat_message("user"):
                st.markdown(user_input)

            st.session_state.questions_asked += 1

            ai_reply = recruiter_chat_ai(
                st.session_state.messages,
                st.session_state.jd_title,
                st.session_state.jd_info,
                profile,
                st.session_state.questions_asked
            )

            st.session_state.messages.append({"role": "assistant", "content": ai_reply})

            with st.chat_message("assistant"):
                st.markdown(ai_reply)

            # Stop after 10 questions
            if st.session_state.questions_asked >= 10:
                st.session_state.chat_complete = True

    # After chat complete
    if st.session_state.chat_complete:
        with st.spinner("Analyzing candidate interest..."):

            interest_data = analyze_interest_ai(str(st.session_state.messages))

            save_to_file(
                name,
                match_score,
                interest_data["score"],
                interest_data["note"]
            )

            total = (match_score + interest_data["score"]) / 2

            if total >= 70 or interest_data["score"] >= 70:
                result = "✅ Moving forward to interview!"
            else:
                result = "❌ Not shortlisted, but saved for future."

            st.success(result)

        # Move to next candidate
        if st.button("➡️ Next Candidate"):
            st.session_state.current_candidate_index += 1
            st.session_state.messages = []
            st.session_state.questions_asked = 0
            st.session_state.chat_complete = False
            st.rerun()

else:
    st.success("🎉 All candidates processed!")