from __future__ import annotations

import time
from typing import Any, Optional
import requests
import structlog

from src.config import settings

logger = structlog.get_logger()

AUTH_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"


class FranceTravailConnector:
    """Connecteur centralisé pour l'authentification et les requêtes vers l'API France Travail."""

    def __init__(self) -> None:
        self.client_id = getattr(settings, "francetravail_client_id", None)
        self.client_secret = getattr(settings, "francetravail_client_secret", None)

        if not self.client_id or not self.client_secret:
            raise ValueError("FRANCETRAVAIL_CLIENT_ID ou FRANCETRAVAIL_CLIENT_SECRET absent de la configuration.")

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def get_valid_token(self) -> Optional[str]:
        """Récupère un jeton OAuth2 valide (avec mise en cache)."""
        # Réutilisation du token s'il est encore valide (avec une marge de 30 secondes)
        if self._access_token and time.time() < (self._token_expires_at - 30):
            return self._access_token

        auth_url = f"{AUTH_URL}?realm=/partenaire"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "api_offresdemploiv2 o2dsoffre",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(auth_url, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            self._access_token = data.get("access_token")
            expires_in = data.get("expires_in", 1499)
            self._token_expires_at = time.time() + expires_in

            logger.info("🔑 Nouveau jeton France Travail généré")
            return self._access_token

        except Exception as exc:
            logger.error("❌ Erreur d'authentification France Travail", error=str(exc))
            return None

    def get(self, url: str, params: Optional[dict[str, Any]] = None) -> Optional[requests.Response]:
        """Effectue une requête GET authentifiée vers l'API France Travail."""
        token = self.get_valid_token()
        if not token:
            logger.error("Impossible d'effectuer la requête GET : jeton manquant.")
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            return response
        except Exception as exc:
            logger.error("❌ Erreur HTTP lors de l'appel France Travail", url=url, error=str(exc))
            return None


# Instance unique (Singleton) à réutiliser dans tout le projet
france_travail_connector = FranceTravailConnector()