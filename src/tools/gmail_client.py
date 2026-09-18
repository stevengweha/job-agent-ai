import os
import re
import base64
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from src.connectors.GmailConnector import GmailConnector
from src.config import settings
from src.llm_client import llm
import structlog

logger = structlog.get_logger()

class GmailClient:
    def __init__(self, connector: Optional[GmailConnector] = None):
        self.connector = connector or GmailConnector()
        self.service = self.connector.service
        self.llm = llm

    def send_direct_email(self, to_email: str, subject: str, body: str, attachment_path: Optional[str] = None) -> bool:
        """Envoie un e-mail brut avec le sujet et le corps fournis sans repasser par le LLM."""
        return self.send_email_with_attachment(
            to_email=to_email,
            subject=subject,
            body=body,
            attachment_path=attachment_path
        )

    def _markdown_to_html(self, text: str) -> str:
        """Convertit le Markdown basique (**gras**, sauts de ligne) en HTML propre."""
        html_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        html_text = html_text.replace('\n', '<br>')
        
        return f"""
        <html>
          <body style="font-family: Arial, sans-serif; font-size: 14px; color: #333333; line-height: 1.6;">
            {html_text}
          </body>
        </html>
        """

    def send_email_with_attachment(self, to_email: str, subject: str, body: str, attachment_path: str = None) -> bool:
        if not self.service:
            logger.warning("Service Gmail non authentifié. Simulation de l'envoi e-mail.", to=to_email, subject=subject)
            return False

        message = MIMEMultipart('mixed')
        message['to'] = to_email
        message['subject'] = subject

        alt_part = MIMEMultipart('alternative')
        alt_part.attach(MIMEText(body, 'plain', 'utf-8'))
        
        html_body = self._markdown_to_html(body)
        alt_part.attach(MIMEText(html_body, 'html', 'utf-8'))

        message.attach(alt_part)

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
            message.attach(part)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        try:
            self.service.users().messages().send(userId="me", body={'raw': raw_message}).execute()
            logger.info("E-mail envoyé avec succès via Gmail", to=to_email)
            return True
        except Exception as e:
            logger.error("Erreur lors de l'envoi de l'e-mail", error=str(e))
            return False

    def generate_and_send_tailored_email(self, company: str, job_title: str, job_description: str, to_email: str = "recrutement@entreprise.com", attachment_path: str = None) -> bool:
        """Utilise le LLM pour rédiger de manière autonome un e-mail de candidature ultra-personnalisé."""
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            
            cand = settings.candidate
            sp = settings.search_profile

            full_name = cand.full_name
            degree = cand.degree
            school = cand.school
            
            candidate_intro = f"Tu es {full_name}"
            if degree != "Non spécifié":
                candidate_intro += f", en formation / diplômé {degree}"
                if school != "Non spécifié":
                    candidate_intro += f" à {school}"
            candidate_intro += "."

            signature = full_name
            if degree != "Non spécifié":
                signature += f", {degree}"
                if school != "Non spécifié":
                    signature += f" ({school})"

            system_prompt = candidate_intro
            user_prompt = f"""
Rédige un e-mail de candidature professionnel, percutant et ultra-personnalisé en français à destination de l'équipe recrutement de l'entreprise "{company}" pour le poste de "{job_title}".

Voici la description de l'offre :
{job_description[:2000]}

Consignes :
- Mets en avant les compétences techniques du candidat qui font écho à l'offre.
- Utilise la syntaxe Markdown **texte** uniquement pour mettre en gras les mots-clés ou technologies clés.
- N'utilise AUCUN placeholder entre crochets (comme [Nom], [Poste], etc.), rédige un e-mail entièrement prêt à l'envoi.
- Signe strictement avec : {signature}

Renvoie uniquement le corps du message (sans le sujet).
"""
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            response = self.llm.invoke(messages)
            body = response.content.strip()

            if "[" in body and "]" in body:
                logger.warning(
                    "⚠️ L'e-mail généré par le LLM contient un placeholder non résolu. "
                    "Repli sur l'e-mail générique de secours.",
                    company=company
                )
                return self.send_follow_up(company=company, to_email=to_email, attachment_path=attachment_path)

            contract_label = sp.contract_types[0] if isinstance(sp.contract_types, list) and sp.contract_types else "Candidature"
            subject = f"Candidature {contract_label} - {job_title} | {company}"

            return self.send_email_with_attachment(
                to_email=to_email,
                subject=subject,
                body=body,
                attachment_path=attachment_path
            )
        except Exception as e:
            logger.error("Erreur lors de la génération dynamique de l'e-mail par l'IA", error=str(e))
            return self.send_follow_up(company=company, to_email=to_email, attachment_path=attachment_path)