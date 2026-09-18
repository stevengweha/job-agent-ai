import logging
from typing import Any
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from src.agent.Chat_Router.chat_router_graph import create_chat_router_graph

logger = logging.getLogger("chat_router")


def extract_text_from_content(content: Any) -> str:
    """Extrait proprement le texte brut depuis 'content', qu'il s'agisse d'une str
    ou d'une liste de blocs (format spécifique à Gemini / langchain-google-genai).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        return "\n".join(parts)
    return str(content) if content is not None else ""


class ChatRouter:
    """Adaptateur de routage pour le Chat Router, encapsulant la logique de graphe et la gestion des états de conversation.
    Fournit une interface simple pour traiter les entrées utilisateur et générer des réponses appropriées,
    en tenant compte de l'état de la conversation et des actions sensibles nécessitant confirmation.
    """

    def __init__(self, model_name: str = None, api_key: str = None):
        self.app = create_chat_router_graph(use_local_sqlite=True)

    def route_intent(self, user_input: str, chat_id: str = None, **kwargs) -> str:
        thread_id = chat_id or "default"
        config = {"configurable": {"thread_id": thread_id}}

        if not user_input or not user_input.strip():
            return "⚠️ Message vide."

        try:
            current_state = self.app.get_state(config)
        except Exception:
            logger.exception("Impossible de lire l'état du thread %s", thread_id)
            return "⚠️ Erreur technique : impossible de récupérer l'état de la conversation."

        try:
            if current_state.next:
                result_state = self.app.invoke(Command(resume=user_input), config=config)
            else:
                result_state = self.app.invoke(
                    {
                        "messages": [HumanMessage(content=user_input)],
                        "pending_action": None,
                        "pending_confirmation_text": None,
                        "user_name": kwargs.get("user_name", "Boss"),
                        "chat_id": chat_id,
                    },
                    config=config
                )
        except Exception as e:
            logger.exception("Erreur d'exécution du graphe pour thread %s", thread_id)
            return f"⚠️ Erreur dans le graphe du routeur : {e}"

        current_state = self.app.get_state(config)
        if current_state.next:
            for task in current_state.tasks:
                if task.interrupts:
                    interrupt_payload = task.interrupts[0].value
                    msg = interrupt_payload.get("message", "Confirmation requise.")
                    return extract_text_from_content(msg)

        updated_messages = result_state.get("messages", [])
        if not updated_messages:
            return "⚠️ Aucune réponse générée."

        last_msg = updated_messages[-1]
        raw_content = last_msg.content if isinstance(last_msg, AIMessage) else last_msg
        return extract_text_from_content(raw_content)