import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq  # Make sure to: pip install groq


client = Groq(api_key=os.getenv("GROQ_API_KEY"))



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CandidateProfile(BaseModel):
    full_name: str
    top_keywords: list[str]
    similar_technical_terms: list[str]
    years_of_experience: int
    current_role: str
    recruiter_brief_insight: str
    source_file: str
class JobDescription(BaseModel):
    job_title: str
    required_keywords: list[str]
    preferred_keywords: list[str]
    min_years_experience: int
    recruiter_jd_summary: str
    source_file: str

@app.get("/get_candidates")
def get_candidates():
    # We use a dictionary now to keep the Name at the 'head' of each record
    candidates_by_name = {} 
    base_path = "./data/resumes/"
    
    if not os.path.exists(base_path):
        return {"error": "Resumes folder not found."}

    files = [f for f in os.listdir(base_path) if f.endswith(".txt")]
    
    for filename in files:
        filepath = os.path.join(base_path, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            raw_text = f.read()
        
        try:
            print(f"--- Parsing Candidate from: {filename} ---")
            
            prompt = f"""
            Analyze this resume and return a JSON object.
            
            REQUIRED SCHEMA:
            {{
              "full_name": "Extract the person's name",
              "top_keywords": ["List 5 key skills"],
              "similar_technical_terms": ["Suggest 5 related terms"],
              "years_of_experience": integer,
              "current_role": "Title",
              "recruiter_brief_insight": "2-sentence professional summary"
            }}
            
            Resume Text:
            {raw_text}
            """

            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are an AI Recruiter. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            data = json.loads(completion.choices[0].message.content)

            # --- Clean up & Nesting Fixes ---
            if "candidateInfo" in data: data = data["candidateInfo"]
            
            # Map values to ensure Pydantic doesn't fail
            name = data.get("full_name") or data.get("name") or f"Unknown_{filename}"
            
            final_data = {
                "full_name": name,
                "top_keywords": data.get("top_keywords", []),
                "similar_technical_terms": data.get("similar_technical_terms", []),
                "years_of_experience": int(data.get("years_of_experience", 0)),
                "current_role": data.get("current_role", "N/A"),
                "recruiter_brief_insight": data.get("recruiter_brief_insight", ""),
                "source_file": filename
            }

            # Create the validated profile
            profile = CandidateProfile(**final_data)
            
            # Use the Name as the key (the "Head") for the dictionary
            candidates_by_name[profile.full_name] = profile.model_dump()
            
            print(f"✅ Successfully integrated: {profile.full_name}")

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            
    return {
        "status": "success",
        "candidate_count": len(candidates_by_name),
        "candidates": candidates_by_name # Name-indexed results
    }

@app.get("/get_job_descriptions")
def get_job_descriptions():
    jds_by_title = {} 
    base_path = "./data/jd/"
    
    if not os.path.exists(base_path):
        os.makedirs(base_path) # Create if doesn't exist
        return {"error": "Folder created. Please add JD .txt files."}

    files = [f for f in os.listdir(base_path) if f.endswith(".txt")]
    
    for filename in files:
        filepath = os.path.join(base_path, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            raw_text = f.read()
        
        try:
            print(f"--- Parsing Job Description: {filename} ---")
            
            prompt = f"""
            Analyze this Job Description and return a JSON object.
            
            REQUIRED SCHEMA:
            {{
              "job_title": "Primary Title",
              "required_keywords": ["List 5 mandatory skills"],
              "preferred_keywords": ["List 'nice to have' skills"],
              "min_years_experience": integer,
              "recruiter_jd_summary": "1-sentence internal summary"
            }}
            
            JD Text:
            {raw_text}
            """

            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are an AI Talent Scout. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            data = json.loads(completion.choices[0].message.content)
            data["source_file"] = filename
            
            jd_profile = JobDescription(**data)
            
            # Use Job Title as the Head of the response
            jds_by_title[jd_profile.job_title] = jd_profile.model_dump()
            
            print(f"✅ Successfully parsed JD: {jd_profile.job_title}")

        except Exception as e:
            print(f"❌ Error processing JD {filename}: {e}")
            
    return {
        "status": "success",
        "jd_count": len(jds_by_title),
        "job_descriptions": jds_by_title
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)