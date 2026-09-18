from typing import TypedDict, List, Dict, Any, Optional, Annotated
from langgraph.graph import add_messages

class MasterAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    
    phase: str  
    pending_count: int
    error_message: Optional[str]
    audit_trail: List[str]
    consecutive_429: int  
    
    candidate_name: Optional[str]
    candidate_school: Optional[str]
    zone_rouge_reject: Optional[int]
    zone_orange_hitl: Optional[int]
    zone_verte_auto_apply: Optional[int]

    raw_description: Optional[Any]
    candidate_cv: Optional[str]
    match_score: Optional[int]
    missing_skills: Optional[List[str]]
    justification: Optional[str]
    cv_optimization_hints: Optional[List[str]]
    company: Optional[str]
    title: Optional[str]
    job_url: Optional[str]
    status: Optional[str]
    tailored_cv_path: Optional[str]
    external_id: Optional[str]
    platform: Optional[str]
    contract_type: Optional[str]
    location: Optional[str]

AgentState = MasterAgentState