import os
from src.agent.graph import graph, processing_app

def generate_graph_images():
    os.makedirs("tests", exist_ok=True)
    
    # Sauvegarde du graphe principal
    try:
        png_data = graph.get_graph().draw_mermaid_png()
        file_path = "tests/job_agent_graph.png"
        with open(file_path, "wb") as f:
            f.write(png_data)
        print(f"✅ Graphe principal exporté : {file_path}")
    except Exception as e:
        print(f"⚠️ Erreur lors de l'export du graphe principal : {e}")

    # Sauvegarde du sous-graphe de traitement
    try:
        sub_png_data = processing_app.get_graph().draw_mermaid_png()
        sub_file_path = "tests/processing_subgraph.png"
        with open(sub_file_path, "wb") as f:
            f.write(sub_png_data)
        print(f"✅ Sous-graphe exporté : {sub_file_path}")
    except Exception as e:
        print(f"⚠️ Erreur lors de l'export du sous-graphe : {e}")

if __name__ == "__main__":
    generate_graph_images()