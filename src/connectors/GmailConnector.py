import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.config import settings
import structlog

logger = structlog.get_logger()
SCOPES = ['https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.readonly']

class GmailConnector:
    """Connecteur pur pour l'authentification et l'accès à l'API Gmail (réutilisable partout)."""

    def __init__(self):
        self.service = self._authenticate()

    def _authenticate(self):
        creds = None
        token_path = getattr(settings, "gmail_token_path", "token.json")
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w") as token_file:
                    token_file.write(creds.to_json())
                logger.info("🔄 Token Gmail rafraîchi avec succès.")
            except Exception as e:
                logger.error("❌ Échec du rafraîchissement du token Gmail. Ré-authentification nécessaire.", error=str(e))
                return None

        return build('gmail', 'v1', credentials=creds) if creds else None