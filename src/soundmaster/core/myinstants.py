"""Small, conservative Myinstants integration.

The service never claims that a sound is commercially redistributable. Callers must
explicitly acknowledge that they have the rights to cache a selected URL.
"""

from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_SEARCH_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class MyInstantResult:
    title: str
    page_url: str
    audio_url: str


class MyInstantsError(RuntimeError):
    """Raised when the public page cannot be read or cached safely."""


def search_myinstants(query: str, timeout: float = 15.0) -> list[MyInstantResult]:
    """Search the public website and return links found in its result page."""

    query = query.strip()
    if not query:
        return []
    url = "https://www.myinstants.com/en/search/?name=" + urllib.parse.quote_plus(query)
    request = urllib.request.Request(url, headers={"User-Agent": "SoundMaster/0.1 (local app)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read(MAX_SEARCH_BYTES).decode("utf-8", errors="replace")
    except Exception as error:
        raise MyInstantsError(f"Recherche Myinstants impossible : {error}") from error
    return parse_search_html(content, "https://www.myinstants.com")


def _is_myinstants_host(host: str | None) -> bool:
    """Allow Myinstants and its official subdomains, never lookalike domains."""

    hostname = (host or "").lower().rstrip(".")
    return hostname == "myinstants.com" or hostname.endswith(".myinstants.com")


def _audio_from_result_block(block: str) -> str | None:
    """Extract playable audio before generic image/source attributes."""

    onclick = re.search(
        r'onclick=["\'][^"\']*(?:playSound|play)\s*\(\s*["\'](?P<url>[^"\']+)',
        block,
        re.IGNORECASE,
    )
    if onclick:
        return onclick.group("url")
    for match in re.finditer(
        r'(?:data-audio|data-src)=["\'](?P<url>[^"\']+)["\']',
        block,
        re.IGNORECASE,
    ):
        return match.group("url")
    for match in re.finditer(r'src=["\'](?P<url>[^"\']+)["\']', block, re.IGNORECASE):
        path = urllib.parse.urlparse(html.unescape(match.group("url"))).path.lower()
        if Path(path).suffix in {".mp3", ".wav", ".ogg"}:
            return match.group("url")
    return None


def parse_search_html(content: str, base_url: str) -> list[MyInstantResult]:
    """Parse current and legacy result markup without executing page scripts."""

    results: list[MyInstantResult] = []
    block_pattern = re.compile(
        r'<(?:div|article)\b[^>]*class=["\'][^"\']*\binstant\b[^"\']*["\'][^>]*>'
        r'(?P<body>.*?)(?=<(?:div|article)\b[^>]*class=["\'][^"\']*\binstant\b|$)',
        re.IGNORECASE | re.DOTALL,
    )
    href_pattern = re.compile(r'href=["\'](?P<href>/en/instant/[^"\']+)["\']', re.IGNORECASE)
    title_pattern = re.compile(
        r'<a\b[^>]*href=["\']/en/instant/[^"\']+["\'][^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in block_pattern.finditer(content):
        body = match.group("body")
        href_match = href_pattern.search(body)
        title_match = title_pattern.search(body)
        audio_value = _audio_from_result_block(body)
        if href_match is None or title_match is None or audio_value is None:
            continue
        page_url = urllib.parse.urljoin(base_url, html.unescape(href_match.group("href")))
        audio_url = urllib.parse.urljoin(base_url, html.unescape(audio_value))
        parsed_audio = urllib.parse.urlparse(audio_url)
        if parsed_audio.scheme != "https" or not _is_myinstants_host(parsed_audio.hostname):
            continue
        title = " ".join(re.sub(r"<[^>]+>", " ", title_match.group("title")).split())
        title = html.unescape(title)
        result = MyInstantResult(title=title, page_url=page_url, audio_url=audio_url)
        if result not in results:
            results.append(result)
    return results[:50]


def cache_audio(
    result: MyInstantResult,
    cache_dir: Path,
    rights_acknowledged: bool,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """Download a selected result into the local cache after an explicit rights check."""

    if not rights_acknowledged:
        raise MyInstantsError("Confirmez que vous disposez des droits avant de mettre ce son en cache.")
    parsed = urllib.parse.urlparse(result.audio_url)
    if parsed.scheme != "https" or not _is_myinstants_host(parsed.hostname):
        raise MyInstantsError("L’URL audio doit pointer vers Myinstants en HTTPS.")
    extension = Path(parsed.path).suffix.lower()
    if extension not in {".mp3", ".wav", ".ogg"}:
        raise MyInstantsError("Format audio non supporté.")
    digest = hashlib.sha256(result.audio_url.encode("utf-8")).hexdigest()[:20]
    destination = cache_dir / f"myinstants-{digest}{extension}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        if progress_callback is not None:
            size = destination.stat().st_size
            progress_callback(size, size)
        return destination
    request = urllib.request.Request(result.audio_url, headers={"User-Agent": "SoundMaster/0.1 (local app)"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=20) as response, temporary.open("wb") as output:
            response_url = response.geturl() if hasattr(response, "geturl") else result.audio_url
            final_url = urllib.parse.urlparse(response_url)
            if final_url.scheme != "https" or not _is_myinstants_host(final_url.hostname):
                raise MyInstantsError("La redirection audio ne pointe plus vers Myinstants en HTTPS.")
            total = 0
            expected = 0
            headers = getattr(response, "headers", None)
            if headers is not None:
                try:
                    expected = int(headers.get("Content-Length", 0) or 0)
                except (TypeError, ValueError):
                    expected = 0
            if progress_callback is not None:
                progress_callback(0, expected)
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise MyInstantsError("Le fichier dépasse la limite de sécurité de 25 Mo.")
                output.write(chunk)
                if progress_callback is not None:
                    progress_callback(total, expected)
        temporary.replace(destination)
    except MyInstantsError:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as error:
        temporary.unlink(missing_ok=True)
        raise MyInstantsError(f"Téléchargement Myinstants impossible : {error}") from error
    return destination
