import time
from datetime import datetime, timedelta
import structlog
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from src.agent.state import MasterAgentState
from src.config import settings
from src.agent.nodes import (
    inspect_environment_node,
    fetch_jobs_node,
    process_jobs_node,
    sleep_or_wait_node,
    analyze_job_node, 
    decide_autonomy_node, 
    save_job_node
)
from src.agent.tools import JOB_AGENT_TOOLS
from src.connectors.telegram_bot import TelegramBot

logger = structlog.get_logger()


def _send_notif(message: str):
    """Fonction utilitaire sécurisée pour envoyer une notification Telegram sans bloquer le graphe."""
    try:
        if not settings.telegram_bot_token:
            return
        bot = TelegramBot()
        target_chat_id = getattr(settings, "telegram_chat_id", None)
        if target_chat_id:
            bot.send_message(message, target_chat_id=target_chat_id)
    except Exception as e:
        logger.warning(f"⚠️ Impossible d'envoyer la notification Telegram : {str(e)}")


def check_if_rejected(state: MasterAgentState) -> str:
    """Aiguillage intelligent : si l'offre a été rejetée en amont, on saute le LLM de décision."""
    if state.get("status") == "REJECTED":
        return "save_job"
    return "decide_autonomy"


def create_processing_subgraph():
    """Sous-graphe unitaire gérant l'analyse ATS, le filtrage amont, et l'autonomie conditionnelle."""
    sub_workflow = StateGraph(MasterAgentState)

    sub_workflow.add_node("analyze_job", analyze_job_node)
    sub_workflow.add_node("decide_autonomy", decide_autonomy_node)
    sub_workflow.add_node("tools", ToolNode(JOB_AGENT_TOOLS))
    sub_workflow.add_node("save_job", save_job_node)

    sub_workflow.set_entry_point("analyze_job")
    
    sub_workflow.add_conditional_edges(
        "analyze_job",
        check_if_rejected,
        {
            "save_job": "save_job",
            "decide_autonomy": "decide_autonomy"
        }
    )

    sub_workflow.add_conditional_edges(
        "decide_autonomy",
        tools_condition,
        {
            "tools": "tools",
            "__end__": "save_job"
        }
    )
    sub_workflow.add_edge("tools", "decide_autonomy")
    sub_workflow.add_edge("save_job", END)

    return sub_workflow.compile()


processing_app = create_processing_subgraph()


def decide_next_step(state: MasterAgentState) -> str:
    return state.get("phase", "inspect")


def create_job_agent_graph():
    workflow = StateGraph(MasterAgentState)

    workflow.add_node("inspect", inspect_environment_node)
    workflow.add_node("fetch", fetch_jobs_node)
    workflow.add_node("process", process_jobs_node)
    workflow.add_node("sleep", sleep_or_wait_node)
    
    workflow.set_entry_point("inspect")

    possible_routes = {
        "inspect": "inspect",
        "fetch": "fetch",
        "process": "process",
        "sleep": "sleep"
    }

    workflow.add_conditional_edges("inspect", decide_next_step, possible_routes)
    workflow.add_conditional_edges("fetch", decide_next_step, possible_routes)
    workflow.add_conditional_edges("process", decide_next_step, possible_routes)
    workflow.add_edge("sleep", "inspect")

    return workflow.compile()


graph = create_job_agent_graph()