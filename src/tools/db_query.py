# src/tools/db_query.py
"""Logique de requêtage de la base de données des offres/candidatures, séparée du
wrapper @tool (src/agent/tools.py), cohérent avec l'organisation de ATSAnalyzer
et CVGenerator : la classe fait le travail, le tool ne fait que l'exposer au LLM."""

from sqlalchemy import text
from src.database import SessionLocal, JobModel, ApplicationModel

class DatabaseQueryTool:
    SORTABLE_COLUMNS = {
        "created_at": JobModel.created_at,
        "ats_score": ApplicationModel.ats_score,
    }

    def query(
        self,
        sql_query: str = None,
        status: str = None,
        company: str = None,
        title: str = None,
        min_score: int = None,
        max_score: int = None,
        order_by: str = "created_at",
        order_direction: str = "desc",
        limit: int = 20
    ) -> str:
        try:
            db = SessionLocal()
            
            # Si le LLM fournit une requête SQL brute
            if sql_query and sql_query.strip().upper().startswith("SELECT"):
                # Sécurité basique : on s'assure que c'est bien un SELECT et on limite les risques
                result = db.execute(text(sql_query))
                rows = result.fetchall()
                db.close()
                if not rows:
                    return f"Aucun résultat pour la requête SQL : {sql_query}"
                formatted = [str(dict(row._mapping)) for row in rows[:limit]]
                return f"=== RÉSULTATS SQL ({len(formatted)}) ===\n" + "\n".join(formatted)

            # Sinon, utilisation des filtres habituels
            query = db.query(JobModel, ApplicationModel).outerjoin(
                ApplicationModel, ApplicationModel.job_id == JobModel.id
            )

            if status:
                query = query.filter(JobModel.status == status)
            if company:
                query = query.filter(JobModel.company.ilike(f"%{company}%"))
            if title:
                query = query.filter(JobModel.title.ilike(f"%{title}%"))
            if min_score is not None:
                query = query.filter(ApplicationModel.ats_score >= min_score)
            if max_score is not None:
                query = query.filter(ApplicationModel.ats_score <= max_score)

            sort_column = self.SORTABLE_COLUMNS.get(order_by, JobModel.created_at)
            if order_direction == "asc":
                query = query.order_by(sort_column.asc())
            else:
                query = query.order_by(sort_column.desc())

            safe_limit = max(1, min(limit or 20, 100))
            rows = query.limit(safe_limit).all()
            db.close()
        except Exception as e:
            return f"⚠️ Impossible d'exécuter la requête : {str(e)}"

        if not rows:
            return "Aucune offre ne correspond aux critères demandés."

        results = []
        for job, app in rows:
            ats = getattr(app, "ats_score", None)
            ats_display = f"{ats}%" if ats is not None else "N/A"
            cv_path = getattr(app, "tailored_cv_path", None) if app else None
            results.append(
                f"- ID: {job.id} | Entreprise : {job.company} | Poste : {job.title} | "
                f"Statut : {job.status} | Score ATS : {ats_display} | CV : {'Oui' if cv_path else 'Non'}"
            )

        return f"=== RÉSULTATS DE LA REQUÊTE ({len(results)} offre(s)) ===\n" + "\n".join(results)