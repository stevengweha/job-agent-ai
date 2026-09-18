import sys
from pathlib import Path

# Fix pour assurer le chargement des modules depuis la racine
sys.path.append(str(Path(__file__).parent.parent))

from src.config import settings
from src.connectors.france_travail import france_travail_connector
from src.scraper.job_fetcher import JobFetcher
from src.database import SessionLocal, JobModel


def test_job_fetcher():
    print("=" * 60)
    print("🚀 TEST DU CONNECTEUR ET DU SCRAPER FRANCE TRAVAIL")
    print("=" * 60)

    # 1. Test direct de l'authentification via le connecteur
    print("\n🔑 TEST DU CONNECTEUR FRANCE TRAVAIL...")
    token = france_travail_connector.get_valid_token()
    if token:
        print("  ✅ Authentification réussie, jeton récupéré.")
    else:
        print("  ❌ Échec d'authentification. Vérifie tes identifiants dans le fichier .env.")
        return

    # 2. Vérification de la configuration
    print("\n📋 PROFIL DE RECHERCHE DÉTECTÉ :")
    titles = getattr(settings.search_profile, "target_titles", [])
    contracts = getattr(settings.search_profile, "contract_types", [])
    locations = getattr(settings.search_profile, "locations", [])
    max_jobs = getattr(settings.search_profile, "max_jobs_per_run", 120)

    print(f"  • Postes recherchés : {titles}")
    print(f"  • Contrats          : {contracts}")
    print(f"  • Localisations     : {locations}")
    print(f"  • Limite globale    : {max_jobs} offres max par run")

    # 3. État de la BDD
    db = SessionLocal()
    try:
        existing_count = db.query(JobModel).count()
        print(f"\n🗄️  OFFRES ACTUELLEMENT EN BDD : {existing_count} offre(s)")
    finally:
        db.close()

    # 4. Exécution du scraper
    print("\n📡 LANCEMENT DU SCRAPING...")
    fetcher = JobFetcher()
    jobs = fetcher.fetch_jobs()

    # 5. Résultat
    print("\n" + "=" * 60)
    print(f"📊 RÉSULTAT : {len(jobs)} NOUVELLE(S) OFFRE(S) EXTRAITE(S)")
    print("=" * 60)

    if not jobs:
        print("\n⚠️ Aucune nouvelle offre extraite (toutes déjà en BDD ou aucun résultat).")
        return

    print("\nAperçu des 5 premières offres :\n")
    for idx, job in enumerate(jobs[:5], 1):
        print(f"--- Offre #{idx} ---")
        print(f"ID Externe   : {job['external_id']}")
        print(f"Titre        : {job['title']}")
        print(f"Entreprise   : {job['company']}")
        print(f"Contrat      : {job['contract_type']}")
        print(f"Localisation : {job['location']}")
        print(f"Lien         : {job['description_url']}")
        print(f"Extrait desc : {job['raw_description'][:100]}...\n")


if __name__ == "__main__":
    test_job_fetcher()