from typing_extensions import Annotated, TypedDict, List, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class ChatRouterState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    pending_action: Optional[dict]
    pending_confirmation_text: Optional[str]
    user_name: str
    chat_id: Optional[str]