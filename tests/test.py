from langchain_groq import ChatGroq
from src.agent.tools import ALL_AGENT_TOOLS
from src.llm_client import llm

###llm = ChatGroq(model_name="openai/gpt-oss-120b", api_key="", temperature=0)
llm_tools = llm.bind_tools(ALL_AGENT_TOOLS, tool_choice="required")
response = llm_tools.invoke("Appelle l'outil action_generate_cv pour Pierre chez Ensimag.")
print(response.tool_calls)   # <- si c'est vide, c'est bien le modèle/provider le coupable
print(response.content)      # <- si le JSON apparaît ici, confirmé