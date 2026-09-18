#src/utils/utils.py

import os
import subprocess
from pathlib import Path
import docx
import structlog

logger = structlog.get_logger()

def read_docx(file_path: str) -> str:
    """Extrait le texte brut du master_cv.docx"""
    try:
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception as e:
        logger.error("❌ Erreur lors de la lecture du fichier docx", file_path=file_path, error=str(e))
        return "Master Data Engineering - Python, SQL, Spark, Airflow, Docker, FastAPI. SUPINFO"


def convert_docx_to_pdf(docx_path: str) -> str:
    """Convertit un fichier DOCX en PDF via LibreOffice CLI (--headless)."""
    input_path = Path(docx_path)
    output_dir = input_path.parent
    pdf_path = input_path.with_suffix(".pdf")

    try:
        cmd = [
            "soffice",
            "--headless",
            "--convert-to", "pdf",
            str(input_path),
            "--outdir", str(output_dir)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if pdf_path.exists():
            logger.info("📄 Conversion DOCX -> PDF réussie via LibreOffice", pdf_path=str(pdf_path))
            return str(pdf_path)
        
        raise FileNotFoundError(f"Le fichier PDF n'a pas été créé : {pdf_path}")
    except Exception as e:
        logger.error("❌ Échec de la conversion PDF via LibreOffice", docx_path=docx_path, error=str(e))
        raise RuntimeError(f"Erreur lors de la conversion PDF via LibreOffice : {e}")