# src/config.py
import os
from pathlib import Path
from typing import List, Optional
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

GROQ_MODEL = "openai/gpt-oss-120b"

BASE_DIR = Path(__file__).resolve().parent.parent

class EducationConfig(BaseModel):
    degree: str
    school: str

class CandidateConfig(BaseModel):
    full_name: str
    email: str
    phone: str
    location: str
    education: Optional[EducationConfig] = None
    summary_template: Optional[str] = None


    @property
    def degree(self) -> str:
        return self.education.degree

    @property
    def school(self) -> str:
        return self.education.school

    @property
    def rhythm(self) -> Optional[str]:
        return self.active_profile.rhythm

class SearchProfile(BaseModel):
    contract_types: List[str]
    target_titles: List[str]
    active_profile_name: Optional[str] = None
    locations: List[str]
    rhythm: Optional[str] = None
    min_ats_score: int = 75
    master_cv_path: str = "./assets/master_cv.docx"
    max_jobs_per_run: int = 120

class AutonomyThresholds(BaseModel):
    zone_verte_auto_apply: int = 85
    zone_orange_hitl: int = 75
    zone_rouge_reject: int = 60

class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/job_agent_db")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")  
    forced_llm_provider: Optional[str] = os.getenv("FORCED_LLM_PROVIDER")  
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
    apify_api_key: str = os.getenv("APIFY_API_KEY", "")
    telegram_bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
    francetravail_client_id: Optional[str] = os.getenv("FRANCETRAVAIL_CLIENT_ID")
    francetravail_client_secret: Optional[str] = os.getenv("FRANCETRAVAIL_CLIENT_SECRET")
    candidate: CandidateConfig
    search_profile: SearchProfile
    autonomy_thresholds: AutonomyThresholds

def load_config() -> Settings:
    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        config_path = BASE_DIR / "config.example.yaml"
    
    with open(config_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)
        
    active_name = raw_data["search_profile"]["active_profile_name"]
    
    flat_data = {
        "candidate": raw_data["candidate"],
        "search_profile": raw_data["search_profile"]["profiles"][active_name],
        "autonomy_thresholds": raw_data["autonomy_thresholds"]
    }
    return Settings(**flat_data)

settings = load_config()