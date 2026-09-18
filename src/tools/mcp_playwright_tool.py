import os
import logging
import asyncio
from typing import List, Optional, Any, Dict
from contextlib import AsyncExitStack

from langchain_core.tools import BaseTool, StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

logger = logging.getLogger("mcp_playwright")


class MCPPlaywrightToolkit:
    """Gestionnaire robuste de la session MCP Playwright pour LangGraph."""

    _instance: Optional["MCPPlaywrightToolkit"] = None

    def __init__(self):
        self.server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@playwright/mcp", "--browser", "chromium"],
            env=os.environ.copy(),
        )
        self._stack: Optional[AsyncExitStack] = None
        self._session: Optional[ClientSession] = None
        self._lock = asyncio.Lock()

    async def get_session(self) -> ClientSession:
        """Garantit l'existence d'une session MCP active de manière thread-safe / async-safe."""
        async with self._lock:
            if self._session is not None:
                return self._session

            self._stack = AsyncExitStack()
            try:
                read, write = await self._stack.enter_async_context(
                    stdio_client(self.server_params)
                )
                session = await self._stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()
                self._session = session
                logger.info("⚡ Session Playwright MCP initialisée et active.")
                return self._session
            except Exception as e:
                logger.error("❌ Échec de la connexion au serveur MCP Playwright : %s", str(e))
                if self._stack:
                    await self._stack.aclose()
                self._stack = None
                self._session = None
                raise e

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Exécute directement une action MCP via la session active."""
        session = await self.get_session()
        result = await session.call_tool(tool_name, arguments)
        return result

    async def close(self):
        """Ferme la session proprement dans le contexte de la tâche courante."""
        async with self._lock:
            if self._stack:
                try:
                    await self._stack.aclose()
                except Exception as e:
                    logger.debug("Fermeture stack MCP : %s", str(e))
                finally:
                    self._stack = None
                    self._session = None
            logger.info("🛑 Session Playwright MCP fermée.")

    @classmethod
    def get_shared_instance(cls) -> "MCPPlaywrightToolkit":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance