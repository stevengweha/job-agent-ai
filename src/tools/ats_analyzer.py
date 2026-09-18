# src/tools/ats_analyzer.py
import json
from pydantic import BaseModel, Field
from src.config import settings
from src.llm_client import llm
import structlog

logger = structlog.get_logger()

MAX_PARSE_RETRIES = 2

class ATSAnalysisResult(BaseModel):
    match_score: int = Field(..., description="Score global de correspondance de 0 à 100")
    technical_fit_score: int = Field(..., description="Score spécifique aux compétences techniques (0-100)")
    experience_fit_score: int = Field(..., description="Score relatif à l'expérience et aux responsabilités (0-100)")
    missing_skills: list[str] = Field(..., description="Compétences requises explicitement dans l'offre mais absentes du CV")
    matching_strengths: list[str] = Field(..., description="Points forts du profil qui correspondent parfaitement à l'offre")
    deal_breakers_detected: list[str] = Field(..., description="Éléments bloquants majeurs s'il y en a (ex: mauvais rythme, techno obligatoire non maîtrisée)")
    justification: str = Field(..., description="Analyse détaillée, argumentée et professionnelle de l'adéquation profil/offre")
    cv_optimization_hints: list[str] = Field(..., description="Recommandations concrètes et mots-clés exacts de l'offre à intégrer pour adapter le CV sans mentir")

class ATSAnalyzer:
    def __init__(self):
        self.llm = llm

    def _extract_json(self, content) -> str:
        if content is None:
            content_str = ""
        elif isinstance(content, str):
            content_str = content
        elif isinstance(content, list):
            extracted_parts = []
            for item in content:
                if isinstance(item, str):
                    extracted_parts.append(item)
                elif isinstance(item, dict):
                    if "text" in item:
                        extracted_parts.append(str(item["text"]))
                    elif "content" in item:
                        extracted_parts.append(str(item["content"]))
                    else:
                        extracted_parts.append(json.dumps(item))
                else:
                    extracted_parts.append(str(item))
            content_str = "".join(extracted_parts)
        elif isinstance(content, dict):
            if "text" in content:
                content_str = str(content["text"])
            elif "content" in content:
                content_str = str(content["content"])
            else:
                content_str = json.dumps(content)
        else:
            content_str = str(content)

        cleaned = content_str.strip()
        if "```json" in cleaned:
            parts = cleaned.split("```json")
            if len(parts) > 1:
                cleaned = parts[1].split("```")[0].strip()
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) > 1:
                cleaned = parts[1].strip()
                
        return cleaned

    def analyze(self, cv_text: str, job_description: str) -> ATSAnalysisResult:
        system_prompt = f"""Tu es un Lead Tech Data Engineer et un ATS (Applicant Tracking System) hautement rigoureux. 
Ton rôle est d'analyser l'adéquation entre le CV d'un candidat et une offre d'emploi technique.

Règles strictes :
- Interdiction formelle d'inventer des compétences ou des expériences non présentes dans le CV.
- Sois exigeant et réaliste : évalue la pertinence des competences.
- Identifie clairement les lacunes techniques (missing_skills) et les points forts (matching_strengths).
- Repère d'éventuels "deal breakers" (exigences rédhibitoires non remplies).

Tu dois renvoyer EXCLUSIVEMENT un objet JSON valide respectant rigoureusement la structure suivante :
{{
  "match_score": int (0 à 100),
  "technical_fit_score": int (0 à 100),
  "experience_fit_score": int (0 à 100),
  "missing_skills": ["compétence 1", "compétence 2"],
  "matching_strengths": ["point fort 1", "point fort 2"],
  "deal_breakers_detected": ["élément bloquant 1"],
  "justification": "Analyse professionnelle détaillée en français expliquant le score global, la pertinence technique et l'alignement avec le profil.",
  "cv_optimization_hints": [
    "Consigne précise 1 pour orienter le résumé ou la mise en valeur (ex: insister sur l'expérience Xx, ou reformuler le projet Yy)",
    "Consigne précise 2 sur les mots-clés de l'offre à aligner"
  ]
}}"""

        user_prompt = f"""
PROFIL RECHERCHÉ / CONTEXTE CIBLE :
- Contrat recherché : {settings.search_profile.contract_types}
- Domaine : {settings.search_profile.target_titles}

CV DU CANDIDAT :
{cv_text}

DESCRIPTION DE L'OFFRE D'EMPLOI :
{job_description}
"""

        from langchain_core.messages import SystemMessage, HumanMessage

        last_error = None
        last_raw_content = "N/A"

        for attempt in range(1, MAX_PARSE_RETRIES + 2):
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            if last_error:
                messages.append(HumanMessage(
                    content=f"Ta réponse précédente n'était pas un JSON valide (erreur : {last_error}). "
                            f"Renvoie UNIQUEMENT le JSON valide, sans aucun texte ni markdown autour."
                ))

            try:
                response = self.llm.invoke(messages)
                content = response.content
                last_raw_content = str(content)
                cleaned = self._extract_json(content)
                data = json.loads(cleaned)
                return ATSAnalysisResult(**data)
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"⚠️ Échec de parsing JSON de l'analyse ATS (tentative {attempt}/{MAX_PARSE_RETRIES + 1})",
                    error=last_error
                )

        logger.error("❌ Analyse ATS impossible après plusieurs tentatives : erreur technique persistante.", error=last_error)
        return ATSAnalysisResult(
            match_score=0,
            technical_fit_score=0,
            experience_fit_score=0,
            missing_skills=["ERREUR_TECHNIQUE_PARSING"],
            matching_strengths=[],
            deal_breakers_detected=["Analyse ATS indisponible suite à une erreur technique répétée (pas un rejet réel de l'offre)"],
            justification=f"⚠️ Erreur technique : impossible d'obtenir une analyse JSON valide. Dernière erreur : {last_error}",
            cv_optimization_hints=[]
        )