import json
import os
import requests
from groq import Groq
from dotenv import load_dotenv
load_dotenv()


os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

CANDIDATES_URL = "https://catalyst-recruiting-agent-1.onrender.com/get_candidates"
JD_URL = "https://catalyst-recruiting-agent-1.onrender.com/get_job_descriptions"

def expand_keywords_with_ai(keyword_list):
    """
    Uses AI to turn ['ELK'] into ['ELK', 'Elasticsearch', 'Logstash', 'Kibana']
    to ensure the Python matching logic doesn't miss synonyms.
    """
    prompt = f"""
    Act as a technical dictionary. For each skill in this list, provide common synonyms, 
    acronyms, or closely related core technologies.
    
    List: {keyword_list}
    
    Return a flat JSON array of all terms (original + synonyms). 
    Example: ["MERN", "MongoDB", "Express", "React", "Node"]
    """
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        # Assuming the AI returns {"keywords": [...]}
        data = json.loads(completion.choices[0].message.content)
        return set(k.lower() for k in data.get("keywords", data.get("result", [])))
    except:
        return set(k.lower() for k in keyword_list)

def calculate_python_scores(candidate, jd):
    # 1. AI Expansion (The "Smart" part)
    # We expand both so we catch "AWS" vs "Amazon Web Services"
    expanded_jd = expand_keywords_with_ai(jd['required_keywords'])
    expanded_cand = expand_keywords_with_ai(candidate['top_keywords'])
    
    # 2. Python Scoring (The "Deterministic" part)
    overlap = expanded_jd.intersection(expanded_cand)
    
    # Keyword Score (Percentage of JD requirements met)
    # We compare against the original count to keep the math grounded
    match_percentage = (len(overlap) / max(len(jd['required_keywords']), 1)) * 100
    
    # Experience Score
    exp_diff = candidate['years_of_experience'] - jd['min_years_experience']
    exp_score = 100 if exp_diff >= 0 else max(0, 100 + (exp_diff * 20))

    match_score = (match_percentage * 0.7) + (exp_score * 0.3)
    
    # Interest Score (Python Logic)
    interest_score = 80 if jd['job_title'].lower() in candidate['current_role'].lower() else 60
    
    return round(match_score, 2), round(interest_score, 2), list(overlap)

def run_agent():
    print("📡 Fetching data...")
    cands = requests.get(CANDIDATES_URL).json().get("candidates", {})
    jds = requests.get(JD_URL).json().get("job_descriptions", {})

    results = {}

    for jd_title, jd_info in jds.items():
        rankings = []
        for name, profile in cands.items():
            m_score, i_score, matches = calculate_hybrid_scores(profile, jd_info)
            
            rankings.append({
                "name": name,
                "match_score": m_score,
                "interest_score": i_score,
                "total_score": round((m_score + i_score) / 2, 2),
                "matched_synonyms": matches,
                "explainability": f"AI identified overlap in: {', '.join(matches)}"
            })
        
        results[jd_title] = sorted(rankings, key=lambda x: x['total_score'], reverse=True)

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    run_agent()