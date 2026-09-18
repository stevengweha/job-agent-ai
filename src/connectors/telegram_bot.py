import re
import requests
import structlog
from typing import Optional, List, Dict, Any
from src.config import settings

logger = structlog.get_logger()


def sanitize_for_telegram(text: Any) -> str:
    """Nettoie le texte pour l'envoi Telegram.

    - Convertit les types complexes (Gemini list blocks) en texte.
    - Filtre les blocs d'outils JSON.
    - Convertit les puces '*' en '•' pour éviter d'ouvrir du gras.
    - Corrige les symboles Markdown orphelins (*, _, `) non refermés.
    """
    if not text:
        return ""

    # 1. Normalisation du type de contenu (si liste Gemini)
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        text = "\n".join(parts)
    elif not isinstance(text, str):
        text = str(text)

    # 2. Retrait des blocs d'appel d'outil JSON internes
    def _strip_tool_call_block(match: re.Match) -> str:
        block_content = match.group(1)
        if re.search(r'"(action|tool)"\s*:', block_content) and re.search(r'"(arguments|parameters)"\s*:', block_content):
            return ""
        return match.group(0)

    text = re.sub(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", _strip_tool_call_block, text, flags=re.DOTALL)
    text = text.strip()

    # 3. Traitement ligne par ligne
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()

        # Supprime les lignes de separation de tableaux (|---|)
        if re.fullmatch(r"\|?[\s:\-|]+\|?", stripped) and "-" in stripped and "|" in stripped:
            continue

        # Convertit les lignes de tableaux en texte lisible
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            cleaned_lines.append(" — ".join(cells))
            continue

        # Titres # ou ## convertis en *Gras*
        heading_match = re.match(r"^#{1,6}\s*(.+)$", stripped)
        if heading_match:
            cleaned_lines.append(f"*{heading_match.group(1)}*")
            continue

        # Convertit les puces '* ' en '• ' pour ne pas ouvrir de balise gras non fermee
        if stripped.startswith("* "):
            line = line.replace("* ", "• ", 1)

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 4. Suppression des balises Markdown orphelines (nombre impair d'occurrences)
    for char in ["*", "_", "`"]:
        if text.count(char) % 2 != 0:
            last_pos = text.rfind(char)
            if last_pos != -1:
                text = text[:last_pos] + text[last_pos + 1:]

    return text


class TelegramBot:
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else None

    def send_message(
        self,
        text: str,
        target_chat_id: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "Markdown"
    ) -> bool:
        chat_to_use = target_chat_id or self.chat_id
        if not self.base_url or not chat_to_use:
            logger.warning("Telegram non configuré ou chat_id manquant, notification ignorée.")
            return False

        text = sanitize_for_telegram(text)

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_to_use,
            "text": text,
            "parse_mode": parse_mode
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            response = requests.post(url, json=payload, timeout=10)
            
            # Si le parsing Markdown échoue, bascule silencieuse en texte brut
            if response.status_code != 200 and parse_mode == "Markdown":
                logger.warning("Échec parsing Markdown Telegram, renvoi en texte brut", status_code=response.status_code)
                payload["parse_mode"] = None
                response = requests.post(url, json=payload, timeout=10)

            if response.status_code != 200:
                logger.error("Échec définitif d'envoi Telegram", status_code=response.status_code, body=response.text)

            return response.status_code == 200
        except Exception as e:
            logger.error("Erreur lors de l'envoi de la notification Telegram", error=str(e))
            return False

    def get_updates(self, offset: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.base_url:
            return []

        url = f"{self.base_url}/getUpdates"
        params = {"timeout": 30}
        if offset:
            params["offset"] = offset

        try:
            response = requests.get(url, params=params, timeout=35)
            if response.status_code == 200:
                data = response.json()
                return data.get("result", [])
        except Exception as e:
            logger.error("Erreur lors de la récupération des updates Telegram", error=str(e))
        return []

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> bool:
        if not self.base_url:
            return False
        url = f"{self.base_url}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error("Erreur lors de l'accusé de réception du callback Telegram", error=str(e))
            return False

    def edit_message_reply_markup(self, chat_id: str, message_id: int, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        if not self.base_url:
            return False
        url = f"{self.base_url}/editMessageReplyMarkup"
        payload = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error("Erreur lors de la modification des boutons Telegram", error=str(e))
            return False

    def send_job_approval_request(self, job_title: str, company: str, score: int, job_id: int, target_chat_id: Optional[str] = None) -> bool:
        text = (
            f"⚠️ *Offre en attente de validation (Zone Orange)*\n\n"
            f"🏢 *Entreprise :* {company}\n"
            f"📌 *Poste :* {job_title}\n"
            f"🎯 *Score ATS :* {score}%\n\n"
            f"Souhaites-tu postuler à cette offre ?"
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Oui, postuler", "callback_data": f"approve_{job_id}"},
                    {"text": "❌ Ignorer", "callback_data": f"reject_{job_id}"}
                ]
            ]
        }

        return self.send_message(text, target_chat_id=target_chat_id, reply_markup=reply_markup)