import logging
from src.agent.Chat_Router.tools_web import action_search_web, action_read_web_pages
from src.agent.Chat_Router.chat_router import ChatRouter

logging.basicConfig(level=logging.INFO)


def run_tests():
    print("=== TEST 1 : Sanitisation et lecture directe d'une URL ===")
    # URL avec préfixe à nettoyer pour valider _sanitize_url
    test_url = "view-source:https://www.welcometothejungle.com/fr/companies/about/jobs/data-engineer-alternance_paris"
    read_result = action_read_web_pages.invoke({
        "urls": [test_url]
    })
    print(read_result[:600] + "\n[...]\n")
    print("\n" + "=" * 50 + "\n")

    print("=== TEST 2 : Recherche web DuckDuckGo ===")
    search_result = action_search_web.invoke({
        "query": "alternance Data Engineer Paris site:indeed.fr",
        "max_results": 3
    })
    print(search_result)
    print("\n" + "=" * 50 + "\n")

    print("=== TEST 3 : ChatRouter — Traitement direct d'une URL ===")
    router = ChatRouter()
    
    url_msg = "Analyse cette offre et dis-moi si elle me correspond : https://www.welcometothejungle.com/fr/companies/about/jobs/data-engineer-alternance_paris"
    print(f"Utilisateur : {url_msg}\n")
    
    response_url = router.route_intent(url_msg, chat_id="test_session_url")
    print(f"Assistant : {response_url}")
    print("\n" + "=" * 50 + "\n")

    print("=== TEST 4 : ChatRouter — Recherche générale ===")
    search_msg = "Cherche-moi des offres d'alternance Data Engineer à Paris sur le web."
    print(f"Utilisateur : {search_msg}\n")
    
    response_search = router.route_intent(search_msg, chat_id="test_session_search")
    print(f"Assistant : {response_search}")


if __name__ == "__main__":
    run_tests()