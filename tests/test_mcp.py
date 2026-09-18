import asyncio
from src.agent.tools import action_apply_via_browser
from src.tools.mcp_playwright_tool import MCPPlaywrightToolkit

async def main():
    print("🚀 Test de navigation et remplissage Playwright MCP...")
    toolkit = MCPPlaywrightToolkit.get_shared_instance()
    
    try:
        result = await action_apply_via_browser.ainvoke({
            "job_url": "https://httpbin.org/forms/post",
            "cv_path": "/app/tests/sample_cv.pdf",
            "form_data": {
                "input[name='custname']": " XXXx",
                "input[name='custemail']": "test@example.com",
                "textarea[name='comments']": "Candidature automatique via agent AI."
            }
        })
        print("\nRésultat :")
        print(result)
    finally:
        await toolkit.close()

if __name__ == "__main__":
    asyncio.run(main())