"""Tous les outils (@tool) que l'agent peut piloter via tool calling, ainsi que la
nomenclature des statuts valides. Séparé de nodes.py pour que la configuration des
capacités de l'agent (ce qu'il PEUT faire) reste distincte de l'orchestration
(comment/quand il les utilise)."""
from typing import Optional, Dict
import json
import asyncio
from langchain_core.tools import tool
from src.tools.ats_analyzer import ATSAnalyzer
from src.tools.cv_generator import CVGenerator
from src.tools.db_query import DatabaseQueryTool
from src.tools.gmail_client import GmailClient
from src.tools.email_parser import GmailFetcher
from src.tools.mcp_playwright_tool import MCPPlaywrightToolkit
import structlog
import asyncio

logger = structlog.get_logger()

VALID_JOB_STATUSES = {
    "NEW", "ANALYZED", "CV_READY", "PENDING_APPROVAL",
    "APPLIED", "REJECTED", "BROWSER_FAILED", "EMAIL_FAILED", "PROCESSING"
}


def extract_text_from_llm_response(response_content) -> str:
    """
    Extrait et normalise le texte brut peu importe le format renvoyé 
    par le LLM (str, dict, list de blocs de contenu, etc.).
    Utile en interne dans les outils ou sous-modules faisant appel à un LLM.
    """
    if response_content is None:
        return ""
    
    if isinstance(response_content, str):
        return response_content
    
    if isinstance(response_content, list):
        extracted = []
        for item in response_content:
            if isinstance(item, str):
                extracted.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    extracted.append(str(item["text"]))
                elif "content" in item:
                    extracted.append(str(item["content"]))
                else:
                    extracted.append(json.dumps(item))
            else:
                extracted.append(str(item))
        return "".join(extracted)
    
    if isinstance(response_content, dict):
        if "text" in response_content:
            return str(response_content["text"])
        if "content" in response_content:
            return str(response_content["content"])
        return json.dumps(response_content)
    
    return str(response_content)


@tool
def action_analyze_ats(cv_text: str, job_description: str) -> str:
    """Analyse la correspondance ATS entre le CV du candidat et une offre d'emploi.
    Renvoie un JSON contenant match_score, technical_fit_score, experience_fit_score,
    missing_skills, matching_strengths, deal_breakers_detected et justification."""
    analyzer = ATSAnalyzer()
    result = analyzer.analyze(cv_text, job_description)
    return json.dumps(result.model_dump(), ensure_ascii=False)


@tool
def action_generate_cv(company: str, title: str, justification: str) -> str:
    """Génère un CV personnalisé au format Word adapté à l'offre d'emploi."""
    generator = CVGenerator()
    cv_path = generator.generate_tailored_cv(company, title, justification)
    return cv_path

@tool
async def action_apply_via_browser(
    job_url: str, 
    cv_path: str, 
    form_data: Optional[Dict[str, str]] = None,
    submit_selector: Optional[str] = None
) -> str:
    """Navigue sur l'offre d'emploi via Playwright MCP, remplit les formulaires
    de candidature (nom, email, etc.), téléverse le CV et soumet le dossier.

    Args:
        job_url: L'URL de l'offre d'emploi.
        cv_path: Le chemin local vers le fichier CV (.pdf, .docx).
        form_data: Dictionnaire optionnel des champs à remplir, ex:
                   {"input[name='fullname']": "Pierre Steve", "input[type='email']": "candidat@email.com"}
        submit_selector: Sélecteur CSS optionnel du bouton pour envoyer la candidature (ex: "button[type='submit']").
    """
    toolkit = MCPPlaywrightToolkit.get_shared_instance()
    logs = []

    try:
        # 1. Navigation vers l'offre d'emploi
        nav_res = await toolkit.execute_tool("browser_navigate", {"url": job_url})
        logs.append(f"1. Navigation : {nav_res}")

        # 2. Capture du snapshot pour analyse de la page
        await toolkit.execute_tool("browser_snapshot", {})
        logs.append("2. Inspection du DOM / Snapshot capturé.")

        # 3. Remplissage automatique des champs du formulaire
        if form_data:
            for selector_or_ref, value in form_data.items():
                try:
                    type_res = await toolkit.execute_tool(
                        "browser_type", 
                        {"target": selector_or_ref, "text": str(value)}
                    )
                    logs.append(f"3. Saisie dans '{selector_or_ref}' : {type_res}")
                except Exception as field_err:
                    logs.append(f"3. ⚠️ Échec de saisie sur '{selector_or_ref}' : {str(field_err)}")
        else:
            logs.append("3. Aucun champ de texte à remplir spécifié.")

        # 4. Téléversement du fichier CV
        upload_res = await toolkit.execute_tool(
            "browser_file_upload", 
            {"paths": [cv_path]}
        )
        
        # Détection de l'absence de modale/champ d'upload
        if hasattr(upload_res, "isError") and upload_res.isError:
            logs.append("4. Upload CV : Pas de sélecteur de fichier actif détecté.")
        else:
            logs.append(f"4. Upload CV : {upload_res}")

        # 5. Clic sur le bouton de soumission (si fourni)
        if submit_selector:
            try:
                click_res = await toolkit.execute_tool(
                    "browser_click", 
                    {"target": submit_selector}
                )
                logs.append(f"5. Soumission via '{submit_selector}' : {click_res}")
            except Exception as submit_err:
                logs.append(f"5. ⚠️ Échec du clic de soumission sur '{submit_selector}' : {str(submit_err)}")

        return f"Séquence de postulation sur {job_url} terminée.\nDétails :\n" + "\n".join(logs)

    except Exception as e:
        logger.error("Erreur lors de la postulation via Playwright MCP : %s", str(e))
        return f"Erreur lors de la postulation via Playwright MCP : {str(e)}"

@tool
def action_reject_offer(reason: str = "Non conforme aux critères d'alternance", offer_url: str = None, **kwargs) -> str:
    """Écarte et rejete définitivement l'offre si elle ne correspond pas au profil ou aux critères d'alternance."""
    details = f" (URL: {offer_url})" if offer_url else ""
    if kwargs:
        extra = ", ".join([f"{k}: {v}" for k, v in kwargs.items()])
        details += f" [{extra}]"
    return f"Offre écartée. Raison : {reason}{details}"


@tool
def action_send_email(company: str, job_title: str, job_description: str, cv_path: str, to_email: str = "recrutement@entreprise.com") -> str:
    """Utilise le client Gmail pour rédiger via l'IA et envoyer un e-mail de candidature avec le CV en pièce jointe."""
    try:
        gmail = GmailClient()
        success = gmail.generate_and_send_tailored_email(
            company=company,
            job_title=job_title,
            job_description=job_description,
            to_email=to_email,
            attachment_path=cv_path
        )
        if success:
            return "E-mail de candidature envoyé avec succès via Gmail."
        else:
            return "Échec de l'envoi de l'e-mail (service Gmail non authentifié ou simulation)."
    except Exception as e:
        return f"Erreur lors de l'envoi de l'e-mail : {str(e)}"


@tool
def action_query_database(
    sql_query: Optional[str] = None,
    status: Optional[str] = None,
    company: Optional[str] = None,
    title: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    order_by: str = "created_at",
    order_direction: str = "desc",
    limit: int = 20
) -> str:
    """Interroge la base de données. 

    STRUCTURE DE LA BASE DE DONNÉES :
    1. Table "jobs" :
       - id (Integer, Primary Key)
       - external_id (String)
       - platform (String)
       - title (String)
       - company (String)
       - contract_type (String)
       - location (String)
       - description_url (Text)
       - raw_description (Text)
       - status (String) -> Valeurs possibles : NEW, ANALYZED, CV_READY, PENDING_APPROVAL, APPLIED, REJECTED, BROWSER_FAILED, EMAIL_FAILED, PROCESSING
       - created_at (DateTime)

    2. Table "applications" :
       - id (Integer, Primary Key)
       - job_id (Integer, Foreign Key vers jobs.id)
       - ats_score (Numeric)
       - missing_skills (JSON)
       - tailored_cv_path (String)
       - audit_trail (JSON)
       - applied_at (DateTime)
       - updated_at (DateTime)
    """
    query_tool = DatabaseQueryTool()
    return query_tool.query(
        sql_query=sql_query,
        status=status,
        company=company,
        title=title,
        min_score=min_score,
        max_score=max_score,
        order_by=order_by,
        order_direction=order_direction,
        limit=limit
    )


@tool
def action_read_recent_emails(max_results: int = 10, query: str = "") -> str:
    """Récupère et lit les derniers e-mails de la boîte de réception Gmail (par exemple les 10 derniers)."""
    try:
        fetcher = GmailFetcher()
        emails = fetcher.fetch_recent_emails(max_results=max_results, query=query)
        if not emails:
            return "Aucun e-mail trouvé."
        return json.dumps(emails, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Erreur lors de la récupération des e-mails : {str(e)}"


@tool
def action_search_email_content(search_query: str) -> str:
    """Recherche des e-mails précis dans Gmail en fonction de mots-clés, d'un nom d'entreprise ou d'un sujet, et retourne leur contenu."""
    try:
        fetcher = GmailFetcher()
        emails = fetcher.fetch_recent_emails(max_results=5, query=search_query)
        if not emails:
            return f"Aucun e-mail correspondant trouvé pour : '{search_query}'."
        return json.dumps(emails, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Erreur lors de la recherche de l'e-mail : {str(e)}"


@tool
def action_send_custom_email(to_email: str, subject: str, body: str, attachment_path: Optional[str] = None) -> str:
    """Envoie un e-mail personnalisé (support, relance, message libre) avec un sujet et un corps de texte déjà rédigés."""
    try:
        gmail = GmailClient()
        success = gmail.send_direct_email(
            to_email=to_email,
            subject=subject,
            body=body,
            attachment_path=attachment_path
        )
        if success:
            return f"E-mail envoyé avec succès à {to_email}."
        else:
            return "Échec de l'envoi de l'e-mail (service Gmail non authentifié)."
    except Exception as e:
        return f"Erreur lors de l'envoi de l'e-mail : {str(e)}"

# Groupements d'outils
JOB_AGENT_TOOLS = [action_generate_cv, action_apply_via_browser, action_send_email, action_reject_offer]
SEARCH_EMAIL_TOOLS = [action_read_recent_emails, action_search_email_content, action_send_custom_email]

# Export global incluant tous les outils (Agent principal + Database + Gmail + Playwright MCP)
CHAT_TOOLS = (
    list(JOB_AGENT_TOOLS)
    + [action_query_database]
    + list(SEARCH_EMAIL_TOOLS)
)