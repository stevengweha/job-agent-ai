import json
import os
from pathlib import Path
from docx import Document
from typing import Optional, List
from src.config import settings
from src.llm_client import llm
from src.utils.utils import convert_docx_to_pdf
import structlog

logger = structlog.get_logger()

MAX_PARSE_RETRIES = 2

class CVGenerator:
    def __init__(self):
        self.master_cv_path = getattr(settings.search_profile, "master_cv_path", "./assets/master_cv.docx")
        self.llm = llm

    def _extract_text_from_doc(self, doc: Document) -> str:
        """Extrait tout le texte brut du document Word pour fournir le contexte au LLM."""
        full_text = []
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        full_text.append(cell.text)
        return "\n".join(full_text)

    def _replace_in_paragraph(self, paragraph, placeholder: str, value: str) -> None:
        """Remplace un placeholder en préservant le formatage (police, taille, gras, etc.)
        du run dans lequel il apparaît, y compris si le placeholder est fragmenté sur
        plusieurs runs par Word."""
        full_text = "".join(run.text for run in paragraph.runs)
        if placeholder not in full_text:
            return

        for run in paragraph.runs:
            if placeholder in run.text:
                run.text = run.text.replace(placeholder, value)
                return

        new_full_text = full_text.replace(placeholder, value)
        if paragraph.runs:
            paragraph.runs[0].text = new_full_text
            for run in paragraph.runs[1:]:
                run.text = ""

    def _extract_json(self, content) -> str:
        if content is None:
            content_str = ""
        elif isinstance(content, str):
            content_str = content
        elif isinstance(content, list):
            extracted_parts = []
            for item in content:
                if isinstance(item, str):
                    extracted_parts.append(item)
                elif isinstance(item, dict):
                    if "text" in item:
                        extracted_parts.append(str(item["text"]))
                    elif "content" in item:
                        extracted_parts.append(str(item["content"]))
                    else:
                        extracted_parts.append(json.dumps(item))
                else:
                    extracted_parts.append(str(item))
            content_str = "".join(extracted_parts)
        elif isinstance(content, dict):
            if "text" in content:
                content_str = str(content["text"])
            elif "content" in content:
                content_str = str(content["content"])
            else:
                content_str = json.dumps(content)
        else:
            content_str = str(content)

        cleaned = content_str.strip()
        if "```json" in cleaned:
            parts = cleaned.split("```json")
            if len(parts) > 1:
                cleaned = parts[1].split("```")[0].strip()
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) > 1:
                cleaned = parts[1].strip()
                
        return cleaned

    def _generate_tailored_modifications(
        self, 
        company_name: str, 
        job_title: str, 
        justification: str, 
        cv_text: str,
        cv_optimization_hints: Optional[List[str]] = None
    ) -> dict:
        """Adapte le résumé et les compétences en s'appuyant directement sur les 
        recommandations chirurgicales (cv_optimization_hints) issues de l'analyse ATS."""
        
        hints_formatted = "\n".join([f"- {hint}" for hint in cv_optimization_hints]) if cv_optimization_hints else "- Aucun hint spécifique, aligne naturellement sur l'offre."

        base_prompt = f"""Tu es un expert en recrutement et en ingénierie de données.
À partir du CV d'origine, de l'offre chez '{company_name}' pour le poste de '{job_title}' 
- Analyse ATS globale : {justification}
- Consignes d'optimisation ciblées (HINTS) :
{hints_formatted}

Et en t'inspirant fidèlement de ce modèle de texte de base :
--- MODÈLE DE BASE ---
{settings.candidate.summary_template}
----------------------

RÈGLE ABSOLUE : Rédige le résumé STRICTEMENT EN FRANÇAIS en intégrant chirurgicalement les mots-clés issus des consignes d'optimisation ci-dessus, tout en conservant le rythme, le style et la personnalité du candidat. Ne jamais inventer de compétences ou d'expériences non présentes dans le CV.

Rédige en JSON strict (sans aucun markdown autour, uniquement du JSON valide) deux modifications :
1. "summary": Le résumé professionnel sur-mesure.
2. "skills": Les compétences techniques à mettre en avant.

Format JSON attendu :
{{
  "summary": "...",
  "skills": "..."
}}"""

        from langchain_core.messages import SystemMessage, HumanMessage

        last_error = None
        for attempt in range(1, MAX_PARSE_RETRIES + 2):
            messages = [
                SystemMessage(content="Tu es un assistant expert qui répond en JSON strict."),
                HumanMessage(content=base_prompt)
            ]
            if last_error:
                messages.append(HumanMessage(
                    content=f"Ta réponse précédente n'était pas un JSON valide (erreur : {last_error}). "
                            f"Renvoie UNIQUEMENT le JSON valide, sans aucun texte ni markdown autour."
                ))

            try:
                response = self.llm.invoke(messages)
                content = getattr(response, "content", response)
                cleaned = self._extract_json(content)
                return json.loads(cleaned)
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"⚠️ Échec de parsing JSON des modifications de CV (tentative {attempt}/{MAX_PARSE_RETRIES + 1})",
                    error=last_error
                )

        logger.error("❌ Génération des modifications de CV impossible après plusieurs tentatives, repli sur le résumé générique.", error=last_error)
        return {
            "summary": settings.candidate.summary_template,
            "skills": "Python, SQL, Apache Airflow, Docker, Git"
        }

    def generate_tailored_cv(
        self, 
        company_name: str, 
        job_title: str, 
        justification: str,
        cv_optimization_hints: Optional[List[str]] = None
    ) -> str:
        """Charge le master CV, adapte le contenu, génère le DOCX temporaire puis renvoie le chemin du PDF produit via LibreOffice."""
        if not Path(self.master_cv_path).exists():
            raise FileNotFoundError(f"Le fichier Master CV est introuvable au chemin : {self.master_cv_path}")

        doc = Document(self.master_cv_path)
        cv_text = self._extract_text_from_doc(doc)

        modifications = self._generate_tailored_modifications(
            company_name, 
            job_title, 
            justification, 
            cv_text, 
            cv_optimization_hints
        )
        new_summary = modifications.get("summary", "")
        new_skills = modifications.get("skills", "")

        placeholders_found = {"{{TAILORED_SUMMARY}}": False, "{{TAILORED_SKILLS}}": False}

        for paragraph in doc.paragraphs:
            for placeholder, value in (("{{TAILORED_SUMMARY}}", new_summary), ("{{TAILORED_SKILLS}}", new_skills)):
                if placeholder in paragraph.text:
                    placeholders_found[placeholder] = True
                self._replace_in_paragraph(paragraph, placeholder, value)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for placeholder, value in (("{{TAILORED_SUMMARY}}", new_summary), ("{{TAILORED_SKILLS}}", new_skills)):
                            if placeholder in paragraph.text:
                                placeholders_found[placeholder] = True
                            self._replace_in_paragraph(paragraph, placeholder, value)

        if not placeholders_found["{{TAILORED_SUMMARY}}"]:
            logger.warning("⚠️ Placeholder {{TAILORED_SUMMARY}} introuvable dans le template master_cv.docx.")
        if not placeholders_found["{{TAILORED_SKILLS}}"]:
            logger.warning("⚠️ Placeholder {{TAILORED_SKILLS}} introuvable dans le template master_cv.docx.")

        output_dir = Path("outputs")
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_company = "".join(c for c in company_name if c.isalnum() or c in (' ', '_')).rstrip().replace(' ', '_')
        docx_output_path = output_dir / f"CV_{settings.candidate.full_name.replace(' ', '_')}_{safe_company}.docx"

        # Sauvegarde du document Word puis conversion unique en PDF
        doc.save(docx_output_path)
        pdf_path = convert_docx_to_pdf(str(docx_output_path))

        # Nettoyage du fichier .docx intermédiaire
        if docx_output_path.exists():
            os.remove(docx_output_path)

        return pdf_path