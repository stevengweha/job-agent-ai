# test_gmail_pipeline.py
from src.tools.email_parser import GmailFetcher, EmailParser

def test_pipeline():
    fetcher = GmailFetcher(token_path="token.json")
    parser = EmailParser()

    emails = fetcher.fetch_recent_emails(max_results=3)
    if not emails:
        print("📭 Aucun nouvel e-mail non lu trouvé dans la boîte de réception.")
        return

    for mail in emails:
        print(f"📬 Reçu de : {mail['sender']}")
        print(f"📌 Sujet : {mail['subject']}")
        
        analysis = parser.parse_recruiter_email(mail['body'])
        print(f"   -> Catégorie : {analysis.category}")
        print(f"   -> Résumé : {analysis.summary}\n" + "-"*40)

if __name__ == "__main__":
    test_pipeline()