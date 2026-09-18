import threading
import time
import json
from pathlib import Path
import structlog
from src.config import settings
from src.connectors.telegram_bot import TelegramBot
from src.agent.Chat_Router.chat_router import ChatRouter
from src.agent.graph import create_job_agent_graph
from src.agent.tools import action_generate_cv, action_apply_via_browser, action_send_email, VALID_JOB_STATUSES
from src.database import init_db, SessionLocal, JobModel, ApplicationModel

logger = structlog.get_logger()

def start_telegram_listener():
    """Démarre le bot Telegram avec support des messages, routeur d'intentions et clics sur boutons (HITL)"""
    if not settings.telegram_bot_token:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN manquant, l'écouteur Telegram ne démarrera pas.")
        return

    bot = TelegramBot()
    router = ChatRouter()

    logger.info("📱 Bot Telegram en cours d'écoute...")
    offset = None

    while True:
        try:
            updates = bot.get_updates(offset=offset)
            for update in updates:
                offset = update["update_id"] + 1

                # 1. Gestion des clics sur les boutons interactifs (HITL) — utilisé par le
                # superviseur autonome pour la Zone Orange (voir src/agent/nodes.py).
                if "callback_query" in update:
                    callback = update["callback_query"]
                    callback_id = callback.get("id")  
                    callback_data = callback.get("data")
                    message = callback.get("message", {})
                    chat_id = str(message.get("chat", {}).get("id"))
                    message_id = message.get("message_id")

                    logger.info("Action bouton Telegram reçue", data=callback_data, chat_id=chat_id)

                    # 🛑 STOPPER LA ROUE DE CHARGEMENT IMMÉDIATEMENT + RETIRER LES BOUTONS
                    bot.answer_callback_query(callback_id, text="Traitement en cours...")
                    if chat_id and message_id:
                        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)

                    if callback_data.startswith("approve_") or callback_data.startswith("reject_"):
                        action, job_id_str = callback_data.split("_")
                        job_id = int(job_id_str)

                        db = SessionLocal()
                        try:
                            job_record = db.query(JobModel).filter(JobModel.id == job_id).first()
                            app_record = db.query(ApplicationModel).filter(ApplicationModel.job_id == job_id).first()

                            if job_record:
                                company = job_record.company
                                title = job_record.title
                                job_url = job_record.description_url
                                raw_desc = job_record.raw_description

                                if action == "approve":
                                    bot.send_message(f"✅ Offre validée pour {company}. Génération du CV sur-mesure et candidature en cours...", target_chat_id=chat_id)

                                    # Récupération de la justification et des hints d'optimisation depuis l'audit trail
                                    justification = "Validation manuelle via Telegram"
                                    cv_optimization_hints = []
                                    if app_record and app_record.audit_trail:
                                        for entry in app_record.audit_trail:
                                            if isinstance(entry, str):
                                                if entry.startswith("HINTS::"):
                                                    try:
                                                        cv_optimization_hints = json.loads(entry.replace("HINTS::", ""))
                                                    except:
                                                        pass
                                                elif not entry.startswith("🔍") and not entry.startswith("💾") and not entry.startswith("🤖"):
                                                    justification = entry

                                    # Génération du CV sur-mesure via CVGenerator en passant les hints chirurgicaux
                                    cv_path = app_record.tailored_cv_path if app_record and app_record.tailored_cv_path else None
                                    if not cv_path or not Path(cv_path).exists():
                                        try:
                                            from src.tools.cv_generator import CVGenerator
                                            generator = CVGenerator()
                                            cv_path = generator.generate_tailored_cv(
                                                company_name=company,
                                                job_title=title,
                                                justification=justification,
                                                cv_optimization_hints=cv_optimization_hints
                                            )
                                            if app_record:
                                                app_record.tailored_cv_path = cv_path
                                                db.commit()
                                        except Exception as cv_err:
                                            logger.error("Erreur génération CV suite validation Telegram", error=str(cv_err))
                                            bot.send_message(f"⚠️ Erreur lors de la génération du CV pour {company}.", target_chat_id=chat_id)
                                            job_record.status = "PENDING_APPROVAL"
                                            db.commit()
                                            continue

                                    # Envoi de la candidature (Navigateur ou E-mail)
                                    if job_url and "linkedin.com" in job_url:
                                        result = action_apply_via_browser.invoke({"job_url": job_url, "cv_path": cv_path})
                                        is_success = "succès" in str(result).lower()
                                        job_record.status = "APPLIED" if is_success else "BROWSER_FAILED"
                                        db.commit()
                                        if is_success:
                                            bot.send_message(f"🚀 Candidature envoyée avec succès via navigateur chez *{company}* !", target_chat_id=chat_id)
                                        else:
                                            bot.send_message(f"⚠️ Échec de la candidature via navigateur pour *{company}* :\n`{result}`", target_chat_id=chat_id)
                                    else:
                                        result = action_send_email.invoke({
                                            "company": company,
                                            "job_title": title,
                                            "job_description": str(raw_desc or ""),
                                            "cv_path": cv_path
                                        })
                                        is_success = "succès" in str(result).lower()
                                        job_record.status = "APPLIED" if is_success else "EMAIL_FAILED"
                                        db.commit()
                                        if is_success:
                                            bot.send_message(f"📧 E-mail de candidature envoyé avec succès à *{company}* !", target_chat_id=chat_id)
                                        else:
                                            bot.send_message(f"⚠️ Échec de l'envoi de l'e-mail pour *{company}* :\n`{result}`", target_chat_id=chat_id)

                                elif action == "reject":
                                    job_record.status = "REJECTED"
                                    db.commit()
                                    bot.send_message(f"❌ Offre ignorée pour {company}.", target_chat_id=chat_id)
                            else:
                                bot.send_message("⚠️ Offre introuvable dans la base de données.", target_chat_id=chat_id)
                        except Exception as db_err:
                            db.rollback()
                            logger.error("Erreur mise à jour statut job via Telegram", error=str(db_err))
                            bot.send_message("❌ Une erreur est survenue lors du traitement de votre choix.", target_chat_id=chat_id)
                        finally:
                            db.close()
                    continue

                # 2. Gestion déléguée des messages texte au ChatRouter.
                if "message" in update and "text" in update["message"]:
                    message = update["message"]
                    text = message["text"]
                    chat_id = str(message["chat"]["id"])
                    user_name = message["from"].get("first_name", "Boss")

                    logger.info("Message Telegram reçu", user=user_name, text=text, chat_id=chat_id)

                    try:
                        reply_text = router.route_intent(text, user_name=user_name, chat_id=chat_id)
                        if not reply_text:
                            reply_text = "J'ai bien pris en compte ta demande."
                        bot.send_message(reply_text, target_chat_id=chat_id)
                    except Exception as router_err:
                        logger.error("Erreur du routeur Telegram", error=str(router_err))
                        bot.send_message(f"J'ai bien reçu ton message : « {text} », mais une erreur est survenue.", target_chat_id=chat_id)

        except Exception as e:
            logger.error("Erreur dans la boucle Telegram", error=str(e))
            time.sleep(5)

def run_autonomous_agent():
    """Exécute le méta-graphe superviseur 100% autonome en arrière-plan."""
    logger.info("🧠 Démarrage du Superviseur Autonome LangGraph...")
    agent = create_job_agent_graph()
    try:
        agent.invoke({
            "phase": "inspect",
            "pending_count": 0,
            "error_message": None,
            "audit_trail": []
        })
    except Exception as e:
        logger.error("🛑 Arrêt critique du Superviseur Autonome", error=str(e))

def main():
    logger.info("🚀 Démarrage de Job Agent AI...")

    try:
        init_db()
        logger.info("🗄️ Base de données initialisée avec succès.")
    except Exception as e:
        logger.error("❌ Erreur lors de l'initialisation de la base de données", error=str(e))

    # 1. Lancement du bot Telegram en arrière-plan (HITL)
    telegram_thread = threading.Thread(target=start_telegram_listener, daemon=True)
    telegram_thread.start()

    # 2. Lancement du Superviseur Autonome LangGraph en arrière-plan
    agent_thread = threading.Thread(target=run_autonomous_agent, daemon=True)
    agent_thread.start()

    logger.info("🟢 Agent Autonome 100% opérationnel.")
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt de l'Agent IA demandé.")

if __name__ == "__main__":
    main()