from langchain_core.messages import HumanMessage, ToolMessage
from src.agent.state import AgentState
from src.agent.nodes import decide_autonomy_node

def test_full_green_zone_sequence():
    # État initial corrigé avec les clés au premier niveau
    state = AgentState(
        messages=[HumanMessage(content="Offre : Data Analyst chez SFIP\nScore ATS : 85%")],
        title="Data Analyst",
        company="SFIP",
        match_score=85,
        status="QUALIFIED",
        justification="Bon profil aligné avec les attentes.",
        job_url="https://example.com/offre-sofi",
        audit_trail=[]
    )
    
    # 1. Premier appel : L'agent doit décider de générer le CV
    res_state_1 = decide_autonomy_node(state)
    last_msg_1 = res_state_1["messages"][-1]
    
    assert len(last_msg_1.tool_calls) > 0, "L'agent n'a déclenché aucun outil."
    assert last_msg_1.tool_calls[0]["name"] == "action_generate_cv", f"Attendu action_generate_cv, reçu {last_msg_1.tool_calls[0]['name']}"
    print("✔ Étape 1 validée : action_generate_cv a bien été appelé.")

    # 2. Simulation du retour de l'outil de génération de CV (ToolMessage)
    tool_msg = ToolMessage(
        content="CV généré et sauvegardé avec succès pour SFIP.",
        tool_call_id=last_msg_1.tool_calls[0]["id"]
    )
    
    # On reconstruit l'état avec l'historique mis à jour
    state_step_2 = AgentState(
        messages=res_state_1["messages"] + [tool_msg],
        title="Data Analyst",
        company="SFIP",
        match_score=85,
        status="QUALIFIED",
        audit_trail=res_state_1.get("audit_trail", [])
    )
    
    # 3. Deuxième appel : Face au résultat du CV, l'agent doit enchaîner sur la postulation
    res_state_2 = decide_autonomy_node(state_step_2)
    last_msg_2 = res_state_2["messages"][-1]
    
    assert len(last_msg_2.tool_calls) > 0, "L'agent s'est arrêté après le CV et n'a pas postulé."
    called_tool_name = last_msg_2.tool_calls[0]["name"]
    
    assert called_tool_name in ["action_send_email", "action_apply_via_browser"], f"Outil de postulation attendu, reçu {called_tool_name}"
    print(f"✔ Étape 2 validée : Enchaînement réussi vers l'outil de postulation ({called_tool_name}).")

if __name__ == "__main__":
    test_full_green_zone_sequence()