"""Nœuds du graphe de traitement d'une offre (analyse, décision, sauvegarde).
Les outils que l'agent pilote via tool calling natif sont définis dans src/agent/tools.py."""

import time
import json
import structlog
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from src.agent.state import AgentState, MasterAgentState
from src.agent.tools import (
    action_analyze_ats,
    VALID_JOB_STATUSES,
    JOB_AGENT_TOOLS,
)
from src.config import settings
from src.llm_client import llm
from src.database import SessionLocal, JobModel, ApplicationModel
from src.connectors.telegram_bot import TelegramBot
from src.scraper.job_fetcher import JobFetcher
from src.utils.utils import read_docx

logger = structlog.get_logger()


def send_telegram_notification(message: str, reply_markup=None):
    """Envoie une notification active sur Telegram si le token et le chat_id sont configurés."""
    if not settings.telegram_bot_token:
        return
    try:
        bot = TelegramBot()
        target_chat_id = getattr(settings, "telegram_chat_id", None)
        if target_chat_id:
            bot.send_message(message, target_chat_id=target_chat_id, reply_markup=reply_markup)
    except Exception as e:
        print(f"⚠️ Erreur d'envoi Telegram : {e}")


def sleep_or_wait_node(state: MasterAgentState) -> MasterAgentState:
    """Étape 4 : Gestion adaptative du temps de repos."""
    if state.get("error_message") == "RATE_LIMIT_429":
        fails = state.get("consecutive_429", 1)
        sleep_duration = min(120 * (2 ** (fails - 1)), 900)
        logger.info(f"⏳ [Agent Autonome] Quota saturé. Pause de sécurité pour {sleep_duration // 60} minutes...")
        time.sleep(sleep_duration)
    else:
        state["consecutive_429"] = 0
        logger.info("💤 [Agent Autonome] Cycle terminé. Mise en veille de 1 heure...")
        time.sleep(3600)

    state["phase"] = "inspect"
    return state


def inspect_environment_node(state: MasterAgentState) -> MasterAgentState:
    """Étape 1 : L'agent audite sa base de données pour compter les offres non traitées."""
    logger.info("🔍 [Agent Autonome] Audit de l'environnement (base de données)...")
    db = SessionLocal()
    try:
        stuck_threshold = datetime.utcnow() - timedelta(minutes=15)
        stuck_jobs = db.query(JobModel).filter(
            JobModel.status == "PROCESSING",
            JobModel.created_at < stuck_threshold
        ).all()
        if stuck_jobs:
            for stuck_job in stuck_jobs:
                stuck_job.status = "NEW"
            db.commit()
            logger.warning(f"♻️ {len(stuck_jobs)} offre(s) bloquée(s) en PROCESSING remises en file.")

        pending_count = db.query(JobModel).filter(JobModel.status == "NEW").count()
        state["pending_count"] = pending_count
        state["error_message"] = None
        logger.info(f"📊 État des stocks : {pending_count} offres en attente.")
    except Exception as e:
        state["pending_count"] = 0
        state["error_message"] = str(e)
        logger.error("❌ Erreur lors de l'audit de la base", error=str(e))
    finally:
        db.close()

    state["phase"] = "process" if state["pending_count"] > 0 else "fetch"
    return state


def process_jobs_node(state: MasterAgentState) -> MasterAgentState:
    """Étape 3 : Dépile et traite TOUTES les offres en attente (NEW) en séquence dans la même session."""
    logger.info("⚙️ [Agent Autonome] Dépilage et traitement de la file d'attente...")
    from src.agent.graph import processing_app, _send_notif
    db = SessionLocal()
    try:
        while True:
            job_record = db.query(JobModel).filter(JobModel.status == "NEW").first()
            if not job_record:
                logger.info("✅ Toutes les offres en attente ont été traitées.")
                break

            job_record.status = "PROCESSING"
            db.commit()

            sub_state = {
                "job_id": job_record.id,
                "messages": [],
                "title": job_record.title,        
                "company": job_record.company,    
                "job_url": job_record.description_url,
                "raw_description": {
                    "title": job_record.title,
                    "companyName": job_record.company,
                    "location": job_record.location,
                    "description": job_record.raw_description,
                    "url": job_record.description_url
                },
                "candidate_cv": settings.search_profile.master_cv_path,
                "audit_trail": [],
                "match_score": 0,
                "status": "PROCESSING"
            }

            res = processing_app.invoke(sub_state)

            final_status = res.get("status", "PENDING_APPROVAL")
            if final_status not in VALID_JOB_STATUSES:
                final_status = "PENDING_APPROVAL"

            score = res.get("match_score", 0)

            # Mise à jour directe de l'état du Job en base
            updated_job = db.query(JobModel).filter(JobModel.id == job_record.id).first()
            if updated_job:
                updated_job.status = final_status
                db.commit()

            _send_notif(f"🎯 *Offre traitée* : {job_record.title} chez {job_record.company}\n📊 Score ATS : {score}% | Statut : `{final_status}`")

            time.sleep(2) 

        remaining = db.query(JobModel).filter(JobModel.status == "NEW").count()
        state["pending_count"] = remaining
        state["consecutive_429"] = 0
        state["phase"] = "process" if remaining > 0 else "sleep"

    except Exception as api_err:
        db.rollback()
        error_str = str(api_err)
        if "429" in error_str or "rate_limit" in error_str.lower():
            logger.warning("⚠️ Limite Groq (429) atteinte. Pause de sécurité...")
            state["phase"] = "sleep"
            state["error_message"] = "RATE_LIMIT_429"
            state["consecutive_429"] = state.get("consecutive_429", 0) + 1
            from src.agent.graph import _send_notif
            _send_notif(f"⚠️ *Alerte Agent* : Surcharge Groq (429). Tentative n°{state['consecutive_429']}.")
        else:
            logger.error("❌ Erreur dans le traitement de la file", error=error_str)
            state["phase"] = "inspect"
    finally:
        db.close()

    return state


def fetch_jobs_node(state: MasterAgentState) -> MasterAgentState:
    """Étape 2 : Si le stock est vide, l'agent lance le scraping et sauvegarde."""
    logger.info("📡 [Agent Autonome] Stock vide. Décision : Lancement du scraping Apify...")
    fetcher = JobFetcher()
    try:
        raw_jobs = fetcher.fetch_jobs()
        if raw_jobs:
            db = SessionLocal()
            try:
                added_count = 0
                for job_data in raw_jobs:
                    job_url = job_data.get("description_url") or job_data.get("url") or job_data.get("link")
                    if not job_url:
                        continue
                    existing = db.query(JobModel).filter(JobModel.description_url == job_url).first()
                    if not existing:
                        new_job = JobModel(
                            external_id=job_data.get("external_id"),
                            platform=job_data.get("platform", "linkedin"),
                            title=job_data.get("title"),
                            company=job_data.get("company"),
                            contract_type=job_data.get("contract_type"),
                            location=job_data.get("location"),
                            description_url=job_url,
                            raw_description=job_data.get("raw_description"),
                            status="NEW"
                        )
                        db.add(new_job)
                        added_count += 1
                db.commit()
                logger.info(f"✅ {added_count} nouvelles offres intégrées et sécurisées.")

                if added_count > 0:
                    from src.agent.graph import _send_notif
                    _send_notif(f"📡 *Scraping terminé* : {added_count} nouvelles offres détectées et stockées en base.")

            except Exception as db_err:
                db.rollback()
                logger.error("❌ Erreur sauvegarde DB", error=str(db_err))
            finally:
                db.close()

        db = SessionLocal()
        state["pending_count"] = db.query(JobModel).filter(JobModel.status == "NEW").count()
        db.close()

        state["phase"] = "process" if state["pending_count"] > 0 else "sleep"
    except Exception as e:
        logger.error("❌ Erreur lors du scraping autonome", error=str(e))
        state["phase"] = "sleep"

    return state


def analyze_job_node(state: AgentState) -> AgentState:
    """Étape 1 : Analyse ATS et filtrage immédiat de la Zone Rouge."""
    print("🔍 [Étape 1/3] Début de l'analyse ATS de l'offre d'emploi...")
    state["audit_trail"].append("🔍 [Étape 1/3] Début de l'analyse ATS de l'offre d'emploi...")

    cv_path = settings.search_profile.master_cv_path
    state["candidate_cv"] = cv_path
    state["candidate_name"] = getattr(settings.candidate, "full_name")
    state["candidate_school"] = getattr(settings.candidate, "school")
    
    state["zone_rouge_reject"] = settings.autonomy_thresholds.zone_rouge_reject
    state["zone_orange_hitl"] = settings.autonomy_thresholds.zone_orange_hitl
    state["zone_verte_auto_apply"] = settings.autonomy_thresholds.zone_verte_auto_apply

    cv_text = read_docx(cv_path)

    raw_desc = state.get("raw_description", "")
    if isinstance(raw_desc, dict):
        job_text_content = raw_desc.get("description") or str(raw_desc)
    else:
        job_text_content = str(raw_desc)

    analysis_raw = action_analyze_ats.invoke({"cv_text": cv_text, "job_description": job_text_content})
    analysis = json.loads(analysis_raw)

    score = analysis["match_score"]
    state["match_score"] = score
    state["missing_skills"] = analysis["missing_skills"]
    state["justification"] = analysis["justification"]
    state["matching_strengths"] = analysis.get("matching_strengths", [])
    state["cv_optimization_hints"] = analysis.get("cv_optimization_hints", [])
    state["deal_breakers_detected"] = analysis.get("deal_breakers_detected", [])

    breakers = analysis["deal_breakers_detected"]

    if score < state["zone_rouge_reject"]:
        state["status"] = "REJECTED"
        msg = f"🚫 [Filtrage Amont] Offre rejetée directement (Score {score}% < {state['zone_rouge_reject']}%)"
        print(msg)
        state["audit_trail"].append(msg)

        company = state.get("company", "Entreprise")
        title = state.get("title", "Poste")
        send_telegram_notification(
            f"🚫 *Offre rejetée* : {title} chez {company}\n"
            f"📊 Score ATS : *{score}%*\n\n"
            f"🧠 *Justification :*\n{breakers}"
        )
    else:
        state["status"] = "QUALIFIED"

    msg = f"✅ [Étape 1/3] Analyse ATS terminée : score de correspondance de {score}%"
    print(msg)
    state["audit_trail"].append(msg)
    return state


def decide_autonomy_node(state: AgentState) -> AgentState:
    """Étape 2 : Le LLM ne traite QUE les offres qualifiées (Zones Orange et Verte)."""
    if state.get("status") == "REJECTED":
        return state

    score = state.get("match_score", 0)
    title = state.get("title")
    company = state.get("company")
    justification = state.get("justification", "")

    raw_desc = state.get("raw_description", "")
    if isinstance(raw_desc, dict):
        job_text_content = raw_desc.get("description") or str(raw_desc)
        job_url = raw_desc.get("url") or state.get("job_url", "")
    else:
        job_text_content = str(raw_desc)
        job_url = state.get("job_url", "")

    start_msg = f"🤖 [Étape 2/3] L'agent analyse la stratégie pour '{title}' chez '{company}' (Score ATS : {score}%)..."
    print(start_msg)
    state["audit_trail"].append(start_msg)

    cv_path = state.get("candidate_cv") or settings.search_profile.master_cv_path
    cv_text = read_docx(cv_path)

    candidate_info = f"""
    Candidat : {settings.candidate.full_name}
    Formation : {settings.candidate.degree} à l'école {settings.candidate.school}
    Profil technique (extrait du CV) :
{cv_text[:1500]}... [CV tronqué pour le contexte]
    Seuils : 
      - Zone Orange (HITL / Amélioration CV) : entre {settings.autonomy_thresholds.zone_orange_hitl}% et {settings.autonomy_thresholds.zone_verte_auto_apply - 1}%
      - Zone Verte (Auto-Apply) : >= {settings.autonomy_thresholds.zone_verte_auto_apply}%
    """

    system_prompt = f"""Tu es l'agent autonome intelligent pilotant la recherche d'alternance.
{candidate_info}

RÈGLES D'OR SUR LES COMPÉTENCES (ANTI-MENSONGE) :
1. BASE-TOI STRICTEMENT SUR LE CV FOURNI ET L'OFFRE. N'invente JAMAIS de compétences, d'années d'expérience ou de technologies que le candidat ne possède pas.
2. LES RAPPROCHEMENTS LOGIQUES SONT AUTORISÉS MAIS SANS MENSONGE : Si une compétence demandée est très proche d'une techno maîtrisée dans le CV (ex: SQL -> PostgreSQL, ou Pandas -> Polars), tu peux faire le pont logiquement. Mais si c'est un outil totalement absent et critique, ne prends pas de liberté.

RÈGLES DE DÉCISION :
1. SI ZONE ORANGE (Score entre {settings.autonomy_thresholds.zone_orange_hitl}% et {settings.autonomy_thresholds.zone_verte_auto_apply - 1}%) :
   - Analyse l'offre pour préparer l'amélioration du CV.
   - Demande l'autorisation (statut PENDING_APPROVAL) mais **N'appelle AUCUN outil**.

2. SI ZONE VERTE (Score >= {settings.autonomy_thresholds.zone_verte_auto_apply}%) :
   - Tu dois exécuter une chaîne d'actions :
     1. Appelle d'abord `action_generate_cv` pour créer le CV sur-mesure.
     2. Analyse le texte de la description d'offre :
        - S'il contient une adresse e-mail de contact/recrutement (ex: contact@company.com, rh@...), extrait cette adresse et appelle `action_send_email` avec l'argument `to_email` rempli.
        - Sinon, si la postulation se fait sur un site/formulaire, appelle `action_apply_via_browser`.
   - **Interdiction absolue de boucler** sur `action_generate_cv` plusieurs fois de suite. Une seule génération suffit, suivie directement de l'outil de postulation.
IMPORTANT : Le texte que tu écris sert uniquement à documenter ton raisonnement pour l'audit. Cela NE remplace JAMAIS un appel d'outil réel. Si tu es en Zone Verte, tu DOIS déclencher un vrai tool call (function calling), jamais écrire le nom de l'outil dans ta réponse textuelle.

CONTRAINTE : Reste concis, utilise du texte en gras avec des astérisques et des emojis pour structurer visuellement. Reste concis et lisible dans un format de chat mobile, Pas de tableaux Markdown.
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("placeholder", "{messages}")
    ])

    try:
        llm_with_tools = llm.bind_tools(JOB_AGENT_TOOLS, tool_choice="auto")
    except TypeError:
        llm_with_tools = llm.bind_tools(JOB_AGENT_TOOLS)

    chain = prompt | llm_with_tools

    messages = state.get("messages", [])
    if not messages:
        initial_content = f"""Poste : {title}
Entreprise : {company}
URL : {job_url}
Score ATS : {score}%
Justification ATS : {justification}

--- DESCRIPTION DE L'OFFRE ---
{job_text_content[:3500]}
"""
        messages = [HumanMessage(content=initial_content)]

    response = chain.invoke({"messages": messages})

    state["messages"] = messages + [response]
    
    tool_calls = getattr(response, "tool_calls", [])
    tool_names = [tc.get("name") for tc in tool_calls] if tool_calls else []

    if score < settings.autonomy_thresholds.zone_verte_auto_apply:
        state["status"] = "PENDING_APPROVAL"
    else:
        if any(name in tool_names for name in ["action_apply_via_browser", "action_send_email"]):
            state["status"] = "APPLIED"
        elif "action_generate_cv" in tool_names:
            state["status"] = "CV_READY"
        else:
            state["status"] = "ANALYZED"

    if response.content:
        reasoning_msg = f"🧠 [Raisonnement de l'Agent] :\n{response.content.strip()}"
        print(reasoning_msg)
        state["audit_trail"].append(reasoning_msg)
        send_telegram_notification(f"🧠 *Analyse de l'Agent* ({company} - {title}) :\n{response.content.strip()}")

    return state


def save_job_node(state: AgentState) -> AgentState:
    """Étape 3 : Enregistre l'offre, l'analyse et l'historique d'audit en base de données."""
    print("💾 [Étape 3/3] Enregistrement des données et de l'audit en base...")
    
    hints = state.get("cv_optimization_hints", [])
    audit_trail = list(state.get("audit_trail", []))
    if hints:
        audit_trail.append(f"HINTS::{json.dumps(hints)}")
    
    state["audit_trail"] = audit_trail
    status = state.get("status", "NEW")
    score = state.get("match_score", 0)

    db = SessionLocal()
    job_id = state.get("job_id")
    try:
        job_url = state.get("job_url") or (state.get("raw_description", {}).get("url") if isinstance(state.get("raw_description"), dict) else "")

        # 1. Recherche par ID prioritaire, puis par URL
        existing_job = None
        if job_id:
            existing_job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not existing_job and job_url:
            existing_job = db.query(JobModel).filter(JobModel.description_url == job_url).first()

        raw_desc = state.get("raw_description", "")
        raw_desc_str = str(raw_desc) if not isinstance(raw_desc, str) else raw_desc

        if not existing_job:
            db_job = JobModel(
                external_id=state.get("external_id"),
                platform=state.get("platform", "linkedin"),
                title=state.get("title", "Data Engineer"),
                company=state.get("company", "Entreprise"),
                contract_type=state.get("contract_type"),
                location=state.get("location"),
                description_url=job_url,
                raw_description=raw_desc_str,
                status=status
            )
            db.add(db_job)
            db.commit()
            db.refresh(db_job)
            job_id = db_job.id
        else:
            job_id = existing_job.id
            existing_job.status = status
            db.commit()

        # 2. Persistance de l'application et du score ATS
        existing_app = db.query(ApplicationModel).filter(ApplicationModel.job_id == job_id).first()
        if not existing_app:
            db_app = ApplicationModel(
                job_id=job_id,
                ats_score=score,
                missing_skills=state.get("missing_skills", []),
                tailored_cv_path=state.get("tailored_cv_path"),
                audit_trail=state.get("audit_trail", [])
            )
            db.add(db_app)
        else:
            existing_app.ats_score = score
            existing_app.missing_skills = state.get("missing_skills", [])
            existing_app.tailored_cv_path = state.get("tailored_cv_path")
            existing_app.audit_trail = state.get("audit_trail", [])

        db.commit()
        print(f"✅ [Étape 3/3] Enregistrement réussi (Score ATS : {score}%).")

    except Exception as e:
        db.rollback()
        print(f"❌ [Étape 3/3] Erreur d'enregistrement DB : {str(e)}")
    finally:
        db.close()

    if status == "PENDING_APPROVAL" and job_id:
        try:
            bot = TelegramBot()
            title = state.get("title", "Poste Data")
            company = state.get("company", "Entreprise")
            target_chat = getattr(settings, "telegram_chat_id", None)

            bot.send_job_approval_request(
                job_title=title,
                company=company,
                score=score,
                job_id=job_id,
                target_chat_id=target_chat
            )
            print("🚀 [Telegram] Alerte interactive (Zone Orange) envoyée avec succès.")
        except Exception as err:
            print(f"⚠️ Erreur lors de l'envoi de l'alerte interactive Telegram : {err}")

    return state