import json
import os
import base64
from typing import Optional
from pydantic import BaseModel, Field
from src.config import settings
from src.connectors.GmailConnector import GmailConnector
from src.llm_client import llm
import structlog

logger = structlog.get_logger()

class GmailFetcher:
    """Outil de recherche et de lecture des e-mails Gmail, utilisant le connecteur centralisé."""
    
    def __init__(self, connector: Optional[GmailConnector] = None):
        self.connector = connector or GmailConnector()
        self.service = self.connector.service

    def fetch_recent_emails(self, max_results: int = 5, query: str = 'is:unread') -> list:
        """Récupère les e-mails correspondant à la requête de la boîte de réception."""
        if not self.service:
            logger.warning("Service Gmail non authentifié. Impossible de récupérer les e-mails.")
            return []

        try:
            results = self.service.users().messages().list(
                userId='me', 
                q=query, 
                maxResults=max_results
            ).execute()
            messages = results.get('messages', [])

            email_list = []
            for msg_meta in messages:
                msg_id = msg_meta['id']
                message = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                
                # Extraction des en-têtes (Sujet, Expéditeur)
                headers = message['payload'].get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'Sans sujet')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Inconnu')

                # Extraction du corps de l'e-mail
                body = self._extract_body(message['payload'])
                
                email_list.append({
                    "id": msg_id,
                    "sender": sender,
                    "subject": subject,
                    "body": body
                })

            return email_list
        except Exception as e:
            logger.error("❌ Erreur lors de la récupération des e-mails Gmail", error=str(e))
            return []

    def _extract_body(self, payload) -> str:
        """Extrait le texte brut du payload de l'e-mail de manière récursive."""
        body = ""
        if 'data' in payload.get('body', {}):
            data = payload['body']['data']
            body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                        break
                elif 'parts' in part:
                    body = self._extract_body(part)
                    if body:
                        break
        return body


MAX_PARSE_RETRIES = 2

class EmailAnalysis(BaseModel):
    category: str = Field(..., description="Catégorie parmi: INTERVIEW_PROPOSAL, REJECTION, MORE_INFO_NEEDED, OTHER")
    summary: str = Field(..., description="Résumé en une phrase de la réponse")

class EmailParser:
    """Analyseur sémantique d'e-mails de recruteurs basé sur le LLM unifié avec validation Pydantic."""
    
    def __init__(self):
        self.llm = llm

    def _extract_json(self, content: str) -> str:
        if "```json" in content:
            return content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            return content.split("```")[1].split("```")[0].strip()
        return content.strip()

    def parse_recruiter_email(self, email_body: str) -> EmailAnalysis:
        """Analyse et classifie un e-mail de recruteur via le LLM avec mécanisme de retry sur le format JSON."""
        prompt = f"""
Analyse cet e-mail de recruteur reçu suite à une candidature.
Classifie-le strictement dans l'une de ces catégories :
- INTERVIEW_PROPOSAL (proposition d'entretien)
- REJECTION (refus)
- MORE_INFO_NEEDED (demande de complément)
- OTHER (autre)

CONTENU DE L'E-MAIL:
{email_body}

Renvoie EXCLUSIVEMENT un JSON valide respectant ce schéma :
{{
  "category": "string",
  "summary": "string"
}}
"""
        from langchain_core.messages import SystemMessage, HumanMessage

        last_error = None
        for attempt in range(1, MAX_PARSE_RETRIES + 2):
            messages = [
                SystemMessage(content="Tu es un assistant expert qui répond en JSON strict."),
                HumanMessage(content=prompt)
            ]
            if last_error:
                messages.append(HumanMessage(
                    content=f"Ta réponse précédente n'était pas un JSON valide (erreur : {last_error}). "
                            f"Renvoie UNIQUEMENT le JSON valide, sans aucun texte ni markdown autour."
                ))

            try:
                response = self.llm.invoke(messages)
                raw_content = response.content.strip()
                cleaned = self._extract_json(raw_content)
                data = json.loads(cleaned)
                return EmailAnalysis(**data)
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"⚠️ Échec de parsing JSON de l'analyse d'e-mail (tentative {attempt}/{MAX_PARSE_RETRIES + 1})",
                    error=last_error
                )

        logger.error("❌ Analyse de l'e-mail impossible après plusieurs tentatives.", error=last_error)
        return EmailAnalysis(
            category="PARSING_ERROR",
            summary=f"⚠️ Erreur technique : impossible d'analyser automatiquement l'e-mail après {MAX_PARSE_RETRIES + 1} tentative(s). Dernière erreur : {last_error}"
        )