import os
import re
import sqlite3
import logging
import docx
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from langgraph.checkpoint.sqlite import SqliteSaver
from src.utils.utils import read_docx
from src.config import settings
from src.llm_client import llm
from src.agent.tools import CHAT_TOOLS
from src.agent.Chat_Router.tools_web import WEB_CHAT_TOOLS
from src.agent.Chat_Router.chat_state import ChatRouterState

logger = logging.getLogger("chat_router")

SENSITIVE_TOOLS = {"action_send_email", "action_apply_via_browser", "action_reject_offer", "action_send_custom_email"}
ALL_CHAT_TOOLS = list(CHAT_TOOLS) + list(WEB_CHAT_TOOLS)

DB_PATH = os.getenv("CHAT_ROUTER_DB_PATH", os.path.join(os.path.dirname(__file__), "checkpoints.db"))
LLM_MAX_RETRIES = 2

_CONFIRM_WORDS = {"oui", "yes", "confirme", "confirmé", "confirmee", "confirmée", "go", "vas-y", "ok", "d'accord", "valide"}
_CANCEL_WORDS = {"non", "no", "annule", "annuler", "stop", "cancel", "abandonne", "pas maintenant"}


def _get_safe_recent_messages(messages: list, max_messages: int = 6) -> list:
    if len(messages) <= max_messages:
        return messages

    slice_start = len(messages) - max_messages
    while slice_start > 0 and not isinstance(messages[slice_start], HumanMessage):
        slice_start -= 1

    return messages[slice_start:]


def _invoke_llm_with_retry(messages, max_retries: int = LLM_MAX_RETRIES):
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return llm.invoke(messages)
        except Exception as e:
            last_err = e
            logger.warning("Appel LLM échoué (tentative %s/%s) : %s", attempt + 1, max_retries + 1, e)
    raise last_err


def _generate_confirmation_message(tool_name: str, tool_args: dict) -> str:
    prompt = f"""Tu es l'assistant de {settings.candidate.full_name}. Tu es sur le point d'exécuter une action SENSIBLE et tu dois demander confirmation à l'utilisateur avant de le faire.

Action à confirmer :
- Outil : {tool_name}
- Arguments : {tool_args}

Rédige un court message de confirmation en français, destiné à Telegram :
- Commence par une alerte (emoji ⚠️).
- Explique clairement, en langage naturel, ce que tu t'apprêtes à faire, en te basant sur les arguments fournis.
- Termine par une question claire demandant confirmation (ex: "Confirmes-tu ?").
- Utilise le formatage Telegram (*gras*, emojis), pas de Markdown avancé.
- Reste concis (3-4 lignes maximum)."""

    try:
        response = _invoke_llm_with_retry([HumanMessage(content=prompt)])
        text = response.content if isinstance(response.content, str) else str(response.content)
        if text.strip():
            return text.strip()
    except Exception:
        logger.exception("Échec génération message de confirmation")

    return f"🚨 *Confirmation requise*\n\nJe m'apprête à exécuter *{tool_name}* avec les paramètres suivants : `{tool_args}`.\n\nConfirmes-tu ?"


def _interpret_confirmation(user_reply: str, tool_name: str, tool_args: dict) -> bool:
    normalized = re.sub(r"[^\w\s'-]", "", user_reply.strip().lower())
    if normalized in _CANCEL_WORDS:
        return False
    if normalized in _CONFIRM_WORDS:
        return True

    prompt = f"""L'utilisateur vient de répondre à une demande de confirmation pour l'action suivante :
- Outil : {tool_name}
- Arguments : {tool_args}

Réponse de l'utilisateur : "{user_reply}"

Est-ce que l'utilisateur confirme l'exécution de cette action ? Réponds STRICTEMENT par un seul mot, sans ponctuation ni explication :
- "OUI" si l'utilisateur confirme clairement
- "NON" si l'utilisateur refuse, annule, ou hésite"""

    try:
        response = _invoke_llm_with_retry([HumanMessage(content=prompt)])
        text = response.content if isinstance(response.content, str) else str(response.content)
        return text.strip().upper().startswith("OUI")
    except Exception:
        return False


def agent_node(state: ChatRouterState) -> dict:
    messages = state["messages"]

    recent_messages = _get_safe_recent_messages(messages, max_messages=6)

    master_cv_path = settings.search_profile.master_cv_path
    cv_text = read_docx(master_cv_path)

    system_prompt = f"""Tu es l'assistant personnel et le routeur intelligent de l'agent de recherche d'alternance de {settings.candidate.full_name}.
Tu disposes des outils d'action de l'agent et de sa base de données.
Nom : {settings.candidate.full_name}
Formation : {settings.candidate.degree} à {settings.candidate.school}
CONTENU DU CV DU CANDIDAT : {cv_text}

CONSIGNES STRICTES POUR LES URLS :
1. Si l'utilisateur fournit une URL, déclenche IMMÉDIATEMENT l'outil `action_read_web_pages` avec cette URL. 
2. Dès que le contenu de la page est extrait, analyse-le directement et résume :
   - Intitulé du poste et la description de l'offre
   - Entreprise et localisation
   - Competences, missions principales
   - Diagnostic : Indique si l'offre correspond au profil et le cv de {settings.candidate.full_name} ({settings.candidate.degree}).

3. Si l'utilisateur demande une recherche générale, utilise `action_search_web` pour trouver des offres pertinentes, puis résume les résultats.
   
   CONTRAINTE : Reste concis, utilise du texte en gras avec des astérisques et des emojis pour structurer visuellement. Reste concis et lisible dans un format de chat mobile, Pas de tableaux Markdown.

"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages")
    ])

    try:
        llm_with_tools = llm.bind_tools(ALL_CHAT_TOOLS)
    except Exception:
        llm_with_tools = llm

    chain = prompt | llm_with_tools
    response = chain.invoke({"messages": recent_messages})

    tool_calls = getattr(response, "tool_calls", None) or []
    for call in tool_calls:
        if call["name"] in SENSITIVE_TOOLS:
            tool_name = call["name"]
            tool_args = call.get("args", {})
            tool_id = call.get("id") or f"call_{tool_name}"
            conf_text = _generate_confirmation_message(tool_name, tool_args)

            return {
                "messages": [],
                "pending_action": {"id": tool_id, "name": tool_name, "args": tool_args},
                "pending_confirmation_text": conf_text,
            }

    return {"messages": [response], "pending_action": None, "pending_confirmation_text": None}


def confirm_node(state: ChatRouterState) -> dict:
    pending_action = state.get("pending_action")
    conf_text = state.get("pending_confirmation_text")

    if not pending_action:
        return {"messages": [AIMessage(content="⚠️ Erreur interne : action introuvable.")], "pending_action": None, "pending_confirmation_text": None}

    if not conf_text:
        conf_text = f"⚠️ Confirmes-tu l'exécution de *{pending_action['name']}* ?"

    user_reply = interrupt({
        "type": "confirmation_required",
        "tool_name": pending_action["name"],
        "tool_args": pending_action["args"],
        "message": conf_text,
    })

    confirmed = _interpret_confirmation(str(user_reply), pending_action["name"], pending_action["args"])

    if not confirmed:
        return {
            "messages": [AIMessage(content="🚫 Action annulée.")],
            "pending_action": None,
            "pending_confirmation_text": None,
        }

    confirmed_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": pending_action["name"],
            "args": pending_action["args"],
            "id": pending_action["id"],
        }]
    )

    return {
        "messages": [confirmed_msg],
        "pending_action": None,
        "pending_confirmation_text": None,
    }


def route_after_agent(state: ChatRouterState) -> str:
    if state.get("pending_action"):
        return "confirm"
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"


def route_after_confirm(state: ChatRouterState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"


def create_chat_router_graph(use_local_sqlite: bool = False):
    """Usine de création du graphe.
    Permet de basculer la persistance locale SQLite sur True pour l'adaptateur de production,
    ou sur False pour le chargement natif par l'API/CLI LangGraph.
    """
    workflow = StateGraph(ChatRouterState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("confirm", confirm_node)
    workflow.add_node("tools", ToolNode(ALL_CHAT_TOOLS))

    workflow.set_entry_point("agent")

    workflow.add_conditional_edges("agent", route_after_agent, {"confirm": "confirm", "tools": "tools", "end": END})
    workflow.add_conditional_edges("confirm", route_after_confirm, {"tools": "tools", "end": END})
    workflow.add_edge("tools", "agent")

    if use_local_sqlite:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        return workflow.compile(checkpointer=checkpointer)

    return workflow.compile()


# Instance globale lue par la commande 'langgraph dev' (sans persistance locale SQLite).
chat_router_app = create_chat_router_graph(use_local_sqlite=False)