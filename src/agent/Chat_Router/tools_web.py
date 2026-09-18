import os
import asyncio
from typing import List, Optional
import re
from urllib.parse import urlparse

import httpx
import trafilatura
import structlog
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from duckduckgo_search import DDGS
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode
from crawl4ai.async_configs import CrawlerRunConfig

logger = structlog.get_logger()

MAX_RESULTS_DEFAULT = 5
MAX_CONTENT_CHARS = 3500

# En-têtes pour simuler un navigateur réel et éviter les blocages anti-bot basiques
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _sanitize_url(url: str) -> Optional[str]:
    """Nettoie et valide une URL avant toute requête HTTP."""
    if not url or not isinstance(url, str):
        return None
    cleaned = re.sub(r'^(view-source:|source:)', '', url.strip(), flags=re.IGNORECASE)
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    parsed = urlparse(cleaned)
    if not parsed.netloc or parsed.scheme not in ("http", "https"):
        return None
    return cleaned


# --- 1. Recherche web générale : DuckDuckGo ---

class SearchWebInput(BaseModel):
    query: str = Field(description="La requête de recherche à exécuter sur DuckDuckGo.")
    max_results: int = Field(default=MAX_RESULTS_DEFAULT, description="Nombre maximum de résultats (1 à 10).")


@tool("action_search_web", args_schema=SearchWebInput)
def action_search_web(query: str, max_results: int = MAX_RESULTS_DEFAULT) -> str:
    """Recherche des pages web sur DuckDuckGo (offres d'emploi, articles, infos entreprise, actualités)."""
    max_results = max(1, min(max_results, 10))
    cleaned_query = re.sub(r'\bsite:\S+', '', query, flags=re.IGNORECASE).strip() or query

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(cleaned_query, max_results=max_results))
    except Exception as e:
        logger.error("duckduckgo_search_failed", query=cleaned_query, error=str(e))
        return f"⚠️ Erreur lors de la recherche : {e}"

    if not results:
        return "Aucun résultat trouvé."

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Sans titre")
        href = _sanitize_url(r.get("href", "")) or r.get("href", "")
        body = (r.get("body", "") or "")[:200]
        lines.append(f"{i}. {title}\n  URL: {href}\n  {body}")

    logger.info("duckduckgo_search_done", query=cleaned_query, results_count=len(results))
    return "\n\n".join(lines)


# --- 2. Lecture de contenu : fallback léger d'abord, Crawl4AI en repli ---

class ReadWebPagesInput(BaseModel):
    urls: List[str] = Field(description="Liste des URLs à lire (1 à 5 URLs max).")


def _read_page_lightweight(url: str) -> Optional[str]:
    """Tentative rapide sans navigateur : httpx + trafilatura."""
    try:
        resp = httpx.get(
            url, timeout=12, follow_redirects=True, headers=HTTP_HEADERS
        )
        resp.raise_for_status()
        extracted = trafilatura.extract(
            resp.text, include_comments=False, include_tables=True, output_format="txt"
        )
        if extracted and len(extracted.strip()) > 100:
            return extracted.strip()
    except Exception as e:
        logger.info("lightweight_read_failed", url=url, error=str(e))
    return None


async def _crawl_urls_heavy(urls: List[str]) -> dict:
    """Crawl4AI (navigateur headless), utilisé uniquement en repli pour les sites dynamic/JS."""
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    results = {}
    async with AsyncWebCrawler(config=browser_config) as crawler:
        tasks = [crawler.arun(url=url, config=run_config) for url in urls]
        crawl_results = await asyncio.gather(*tasks, return_exceptions=True)
        for url, res in zip(urls, crawl_results):
            if isinstance(res, Exception) or not getattr(res, "success", False):
                results[url] = None
                continue
            content = (res.markdown or "").strip()
            results[url] = content if content else None
    return results


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return executor.submit(asyncio.run, coro).result()


@tool("action_read_web_pages", args_schema=ReadWebPagesInput)
def action_read_web_pages(urls: List[str]) -> str:
    """Lit le contenu réel d'une ou plusieurs pages web à partir de leurs URLs.
    Nettoie automatiquement les URLs et extrait le texte principal de la page."""
    if not urls:
        return "⚠️ Aucune URL fournie."

    valid_urls = []
    for u in urls:
        clean = _sanitize_url(u)
        if clean and clean not in valid_urls:
            valid_urls.append(clean)

    if not valid_urls:
        return "⚠️ Aucune URL valide fournie."

    valid_urls = valid_urls[:5]
    final_content = {}
    heavy_needed = []

    for url in valid_urls:
        content = _read_page_lightweight(url)
        if content:
            final_content[url] = content
        else:
            heavy_needed.append(url)

    if heavy_needed:
        logger.info("falling_back_to_crawl4ai", urls=heavy_needed)
        try:
            heavy_results = _run_async(_crawl_urls_heavy(heavy_needed))
            for url, content in heavy_results.items():
                final_content[url] = content
        except Exception as e:
            logger.error("crawl4ai_failed", urls=heavy_needed, error=str(e))
            for url in heavy_needed:
                final_content.setdefault(url, None)

    chunks = []
    for url in valid_urls:
        content = final_content.get(url)
        if not content:
            chunks.append(f"### {url}\n⚠️ Impossible d'extraire le contenu de cette page.")
            continue
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS] + "\n[... contenu tronqué ...]"
        chunks.append(f"### {url}\n{content}")

    logger.info("read_web_pages_done", requested=len(valid_urls), success=sum(1 for v in final_content.values() if v))
    return "\n\n---\n\n".join(chunks)


WEB_CHAT_TOOLS = [action_search_web, action_read_web_pages] 