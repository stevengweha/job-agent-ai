from __future__ import annotations

import re
import time
from typing import Any
import structlog

from src.config import settings
from src.connectors.france_travail import france_travail_connector
from src.database import SessionLocal, JobModel

logger = structlog.get_logger()

SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


class JobFetcher:
    """Récupère et filtre dynamiquement les offres d'emploi selon la configuration YAML."""

    def __init__(self) -> None:
        self.connector = france_travail_connector

    def _get_locations(self) -> list[str]:
        locations = getattr(settings.search_profile, "locations", [])
        if locations:
            return [str(loc).strip() for loc in locations if str(loc).strip()]
        candidate_loc = getattr(settings.candidate, "location", None)
        return [str(candidate_loc).strip()] if candidate_loc else ["France"]

    def _get_max_limit(self) -> int:
        return max(1, min(getattr(settings.search_profile, "max_jobs_per_run", 120), 150))

    def _clean_title_keyword(self, title: str) -> str:
        """Extrait le nom pur du métier sans préfixe de contrat."""
        cleaned = re.sub(
            r"\b(a*alternant[e]?|a*alternance|stage|stagiaire|cdi|cdd|intérim|interim)\b",
            "",
            title,
            flags=re.IGNORECASE,
        )
        return " ".join(cleaned.split()).strip()

    def _search_jobs(self, title: str, contract: str, location: str, max_results: int) -> list[dict]:
        clean_title = self._clean_title_keyword(title)
        contract_lower = contract.lower()

        params: dict[str, Any] = {
            "range": f"0-{min(max_results - 1, 149)}",
        }

        # Construction intelligente des paramètres d'API
        if "alternance" in contract_lower or "apprentissage" in contract_lower:
            params["motsCles"] = f"{clean_title} alternance".strip()
            params["natureContrat"] = "E1,E2"
        elif "stage" in contract_lower:
            params["motsCles"] = f"{clean_title} stage".strip()
            params["natureContrat"] = "FS"
        elif contract.upper() in ["CDI", "CDD", "MIS"]:
            params["motsCles"] = clean_title
            params["typeContrat"] = contract.upper()
        else:
            params["motsCles"] = clean_title

        # Mapping de localisation (Codes INSEE / Régions)
        loc_lower = location.lower()
        if loc_lower == "paris":
            params["commune"] = "75056"
        elif loc_lower in ["île-de-france", "ile-de-france", "idf"]:
            params["region"] = "11"
        elif loc_lower not in ["france", "national"]:
            params["motsCles"] = f"{params['motsCles']} {location}".strip()

        response = self.connector.get(SEARCH_URL, params=params)
        if response is None:
            return []

        if response.status_code in (200, 206):
            return response.json().get("resultats", [])
        elif response.status_code == 204:
            return []
        else:
            logger.warning(
                "⚠️ Code statut inattendu",
                status=response.status_code,
                details=response.text,
                params=params,
            )
            return []

    def _is_contract_matching(
        self, job_title: str, job_contract_label: str, raw_desc: str, target_contracts: list[str]
    ) -> bool:
        """Vérification hybride (Type de contrat + Titre + Description) pour détecter les offres."""
        full_text = f"{job_title} {job_contract_label} {raw_desc}".lower()

        for target in target_contracts:
            target_lower = target.lower()

            if "alternance" in target_lower or "apprentissage" in target_lower:
                keywords = ["alternant", "alternance", "apprentissage", "professionnalisation"]
                if any(k in full_text for k in keywords):
                    return True

            elif "stage" in target_lower:
                keywords = ["stage", "stagiaire", "internship"]
                if any(k in full_text for k in keywords):
                    return True

            elif target_lower in full_text:
                return True

        return False

    def _process_jobs(self, raw_jobs: list[dict], max_limit: int, target_contracts: list[str]) -> list[dict]:
        jobs: list[dict] = []
        seen_ids: set[str] = set()

        db = SessionLocal()
        try:
            existing_records = db.query(JobModel.external_id).all()
            existing_db_ids = {r.external_id for r in existing_records if r.external_id}
        finally:
            db.close()

        skipped_db_duplicates = 0
        skipped_wrong_contract = 0

        for item in raw_jobs:
            job_id = str(item.get("id")) if item.get("id") else None
            if not job_id or job_id in seen_ids:
                continue

            if job_id in existing_db_ids:
                skipped_db_duplicates += 1
                continue

            job_title = item.get("intitule", "")
            contract_label = item.get("typeContratLibelle") or item.get("typeContrat") or ""
            raw_description = item.get("description", "")

            # Validation multicritère de l'offre
            if not self._is_contract_matching(job_title, contract_label, raw_description, target_contracts):
                skipped_wrong_contract += 1
                continue

            seen_ids.add(job_id)

            company_info = item.get("entreprise", {})
            location_info = item.get("lieuTravail", {})
            origin_url = (
                item.get("origineOffre", {}).get("urlOrigine")
                or f"https://candidat.francetravail.fr/offres/recherche/detail/{job_id}"
            )

            structured_job = {
                "external_id": job_id,
                "platform": "francetravail",
                "title": job_title,
                "company": company_info.get("nom", "Entreprise confidentielle"),
                "contract_type": contract_label,
                "location": location_info.get("libelle", "Non précisé"),
                "description_url": origin_url,
                "raw_description": raw_description,
                "status": "NEW",
            }

            jobs.append(structured_job)
            if len(jobs) >= max_limit:
                break

        logger.info(
            "📊 Filtrage des offres terminé",
            offres_retenues=len(jobs),
            ignores_car_deja_en_db=skipped_db_duplicates,
            ignores_car_mauvais_contrat=skipped_wrong_contract,
        )

        return jobs

    def fetch_jobs(self) -> list[dict]:
        logger.info("🔎 Démarrage du scraping ciblé via FranceTravailConnector")

        if not self.connector.get_valid_token():
            return []

        max_limit = self._get_max_limit()
        target_titles = getattr(settings.search_profile, "target_titles", [])
        contract_types = getattr(settings.search_profile, "contract_types", [])
        locations = self._get_locations()

        if not target_titles or not contract_types:
            logger.warning("⚠️ Aucun titre ou type de contrat configuré.")
            return []

        all_raw_jobs: list[dict] = []
        total_queries = len(target_titles) * len(contract_types) * len(locations)
        limit_per_query = max(5, max_limit // max(1, total_queries))

        for contract in contract_types:
            for title in target_titles:
                for location in locations:
                    logger.info("🎯 Requête ciblée", title=title, contract=contract, location=location)
                    results = self._search_jobs(
                        title=title,
                        contract=contract,
                        location=location,
                        max_results=limit_per_query,
                    )
                    all_raw_jobs.extend(results)
                    time.sleep(0.12)

        jobs = self._process_jobs(all_raw_jobs, max_limit=max_limit, target_contracts=contract_types)
        logger.info("🏁 Scraping terminé", offres_recuperees=len(jobs))
        return jobs