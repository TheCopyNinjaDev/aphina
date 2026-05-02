"""
Proxy manager for OpenRouter requests.

Parses proxies.txt, rotates proxies on failure, resets the failed list
when all proxies are exhausted so the cycle repeats.
"""

import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar, Callable, Awaitable

import httpx
from openai import AsyncOpenAI, APIStatusError

from app.config import settings

# Status codes that are proxy-specific (wrong region, blocked, overloaded).
# These should trigger rotation to a different proxy.
_PROXY_ERRORS = {403, 429, 500, 502, 503, 504}

# Status codes that are request-level (bad auth, invalid params).
# Retrying with another proxy won't help.
_FATAL_CODES = {400, 401, 422}

logger = logging.getLogger(__name__)

T = TypeVar("T")

PROXIES_FILE = Path(__file__).parent / "proxies.txt"


@dataclass
class Proxy:
    country: str
    ip: str
    http_port: int
    socks5_port: int
    login: str
    password: str

    @property
    def http_url(self) -> str:
        return f"http://{self.login}:{self.password}@{self.ip}:{self.http_port}"

    @property
    def socks5_url(self) -> str:
        return f"socks5://{self.login}:{self.password}@{self.ip}:{self.socks5_port}"

    def __str__(self) -> str:
        return f"{self.ip}:{self.http_port} ({self.country})"

    def __hash__(self) -> int:
        return hash(self.ip)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Proxy) and self.ip == other.ip


def _parse_proxies(filepath: Path) -> list[Proxy]:
    if not filepath.exists():
        logger.warning(f"Proxy file not found: {filepath}")
        return []

    text = filepath.read_text(encoding="utf-8")
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]
    proxies: list[Proxy] = []

    for block in blocks:
        try:
            country_match = re.match(r"^.+?(.+?):", block)
            country = country_match.group(1).strip() if country_match else "Unknown"

            ip = re.search(r"IP:\s*(\S+)", block).group(1)

            ports = re.search(r"Порт\s+\S+:\s*(\d+)/(\d+)", block)
            http_port = int(ports.group(1))
            socks5_port = int(ports.group(2))

            login = re.search(r"Логин:\s*(\S+)", block).group(1)
            password = re.search(r"Пароль:\s*(\S+)", block).group(1)

            proxies.append(Proxy(
                country=country,
                ip=ip,
                http_port=http_port,
                socks5_port=socks5_port,
                login=login,
                password=password,
            ))
        except Exception as e:
            logger.debug(f"Skipped proxy block (parse error): {e}")

    return proxies


def _make_openai_client(proxy: Proxy | None) -> AsyncOpenAI:
    """Create an AsyncOpenAI client pointed at OpenRouter, optionally via proxy."""
    kwargs: dict = {
        "api_key": settings.OPENROUTER_API_KEY,
        "base_url": settings.OPENROUTER_BASE_URL,
        "default_headers": {
            "HTTP-Referer": settings.APP_URL,
            "X-Title": settings.APP_NAME,
        },
    }
    if proxy:
        kwargs["http_client"] = httpx.AsyncClient(proxy=proxy.http_url)
    return AsyncOpenAI(**kwargs)


class ProxyManager:
    def __init__(self, filepath: Path = PROXIES_FILE):
        self._all: list[Proxy] = _parse_proxies(filepath)
        self._failed: set[Proxy] = set()

        if self._all:
            logger.info(f"Loaded {len(self._all)} proxies from {filepath.name}")
        else:
            logger.warning("No proxies loaded — requests will go direct")

    # ------------------------------------------------------------------

    @property
    def has_proxies(self) -> bool:
        return bool(self._all)

    def _available(self, exclude: set[Proxy]) -> list[Proxy]:
        return [p for p in self._all if p not in self._failed and p not in exclude]

    def _pick(self, exclude: set[Proxy]) -> Proxy | None:
        pool = self._available(exclude)
        if not pool:
            # All proxies have been marked failed — reset and try again
            logger.warning("All proxies failed, resetting failed list and retrying")
            self._failed.clear()
            pool = self._available(exclude)
        return random.choice(pool) if pool else None

    def mark_failed(self, proxy: Proxy) -> None:
        logger.warning(f"Proxy failed: {proxy}")
        self._failed.add(proxy)

    # ------------------------------------------------------------------

    async def call(
        self,
        fn: Callable[[AsyncOpenAI], Awaitable[T]],
        max_retries: int = 3,
    ) -> T:
        """
        Execute fn(client) where client uses a random proxy.
        On any exception, marks the proxy failed and retries with another one.
        Falls back to a direct (no-proxy) call if all retries are exhausted.
        """
        if not self.has_proxies:
            return await fn(_make_openai_client(None))

        tried: set[Proxy] = set()
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            proxy = self._pick(tried)

            if proxy is None:
                break  # no more proxies to try

            tried.add(proxy)
            client = _make_openai_client(proxy)
            logger.debug(f"Attempt {attempt}/{max_retries} via {proxy}")

            try:
                return await fn(client)
            except APIStatusError as exc:
                if exc.status_code in _FATAL_CODES:
                    raise  # auth/bad-request errors won't be fixed by another proxy
                last_exc = exc
                self.mark_failed(proxy)
                logger.warning(
                    f"Attempt {attempt} via {proxy} failed: "
                    f"{type(exc).__name__}: {exc}"
                )
            except Exception as exc:
                last_exc = exc
                self.mark_failed(proxy)
                logger.warning(
                    f"Attempt {attempt} via {proxy} failed: "
                    f"{type(exc).__name__}: {exc}"
                )

        # Last resort: direct connection
        logger.warning("All proxy attempts failed — trying direct connection")
        try:
            return await fn(_make_openai_client(None))
        except Exception as exc:
            raise exc if last_exc is None else last_exc

    async def call_http(
        self,
        fn: Callable[[httpx.AsyncClient], Awaitable[T]],
        max_retries: int = 3,
    ) -> T:
        """
        Same retry logic as `call`, but passes a raw httpx.AsyncClient with
        proxy configured. Use this for endpoints where the OpenAI SDK parses
        the response incorrectly (e.g. OpenRouter /images/generations).
        """
        if not self.has_proxies:
            async with httpx.AsyncClient(timeout=60.0) as http:
                return await fn(http)

        tried: set[Proxy] = set()
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            proxy = self._pick(tried)
            if proxy is None:
                break

            tried.add(proxy)
            logger.debug(f"HTTP attempt {attempt}/{max_retries} via {proxy}")

            async with httpx.AsyncClient(proxy=proxy.http_url, timeout=60.0) as http:
                try:
                    return await fn(http)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in _FATAL_CODES:
                        raise
                    last_exc = exc
                    self.mark_failed(proxy)
                    logger.warning(f"HTTP attempt {attempt} via {proxy} failed: {type(exc).__name__}: {exc}")
                except Exception as exc:
                    last_exc = exc
                    self.mark_failed(proxy)
                    logger.warning(f"HTTP attempt {attempt} via {proxy} failed: {type(exc).__name__}: {exc}")

        logger.warning("All HTTP proxy attempts failed — trying direct connection")
        async with httpx.AsyncClient(timeout=60.0) as http:
            try:
                return await fn(http)
            except Exception as exc:
                raise exc if last_exc is None else last_exc


# Singleton used across the app
proxy_manager = ProxyManager()
