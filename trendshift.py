#!/usr/bin/env python3
"""Lê o ranking de repositórios em tendência do Trendshift e imprime JSON.

O site é uma aplicação Next.js. A lista vem no payload da página
(self.__next_f.push), com estrelas, forks e a variação do período.
Se esse payload mudar, o script usa o JSON-LD público como reserva.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE_URL = "https://trendshift.io"
PERIODS = {
    "today": f"{BASE_URL}/",
    "weekly": f"{BASE_URL}/weekly",
    "monthly": f"{BASE_URL}/monthly",
    "yearly": f"{BASE_URL}/yearly",
}
USER_AGENT = "trendshift-reader/1.0 (+https://trendshift.io)"
WINDOW_KEYS = ("date", "year", "month", "week", "week_start")


def ssl_context() -> ssl.SSLContext:
    """Usa o armazenamento padrão e, no macOS, o bundle do sistema."""
    try:
        context = ssl.create_default_context()
        # Força o handshake a falhar cedo se o bundle padrão estiver vazio.
        if context.cert_store_stats().get("x509_ca", 0) > 0:
            return context
    except ssl.SSLError:
        pass

    for path in (
        os.environ.get("SSL_CERT_FILE", ""),
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
    ):
        if path and os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


def fetch_html(url: str, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, "replace")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Trendshift respondeu {exc.code} em {url}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Não foi possível acessar {url}: {exc.reason}") from exc


def _json_at(text: str, index: int) -> Any:
    value, _end = json.JSONDecoder().raw_decode(text, index)
    return value


def repositories_from_flight(html: str) -> list[dict[str, Any]] | None:
    needle = "self.__next_f.push("
    start = 0
    while True:
        index = html.find(needle, start)
        if index < 0:
            return None
        try:
            payload = _json_at(html, index + len(needle))
        except json.JSONDecodeError:
            start = index + len(needle)
            continue
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], str):
            start = index + len(needle)
            continue
        body = payload[1]
        marker = body.find('"initialData":')
        if marker < 0:
            start = index + len(needle)
            continue
        bracket = body.find("[", marker)
        if bracket < 0:
            return None
        try:
            data = _json_at(body, bracket)
        except json.JSONDecodeError:
            return None
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict) and item.get("full_name")]
        start = index + len(needle)


def repositories_from_jsonld(html: str) -> list[dict[str, Any]] | None:
    marker = '<script type="application/ld+json">'
    start = 0
    while True:
        index = html.find(marker, start)
        if index < 0:
            return None
        end = html.find("</script>", index)
        if end < 0:
            return None
        raw = html[index + len(marker) : end]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = end
            continue
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            repos: list[dict[str, Any]] = []
            for entry in data.get("itemListElement") or []:
                item = entry.get("item") if isinstance(entry, dict) else None
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                author = item.get("author") if isinstance(item.get("author"), dict) else {}
                keywords = item.get("keywords") or []
                repos.append(
                    {
                        "rank": entry.get("position"),
                        "full_name": item.get("name"),
                        "repository_id": _repository_id(entry.get("url")),
                        "repository_description": item.get("description") or "",
                        "repository_language": item.get("programmingLanguage"),
                        "language": item.get("programmingLanguage"),
                        "repository_created_at": item.get("dateCreated"),
                        "tags": [{"display_name": keyword} for keyword in keywords if isinstance(keyword, str)],
                        "author_url": author.get("url"),
                    }
                )
            return repos
        start = end


def _repository_id(url: Any) -> int | None:
    if not isinstance(url, str):
        return None
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def normalize(repo: dict[str, Any]) -> dict[str, Any]:
    full_name = repo.get("full_name") or ""
    repository_id = repo.get("repository_id")
    tags = []
    for tag in repo.get("tags") or []:
        if isinstance(tag, dict):
            label = tag.get("display_name") or tag.get("name")
        else:
            label = tag
        if isinstance(label, str) and label.strip():
            tags.append(label.strip())

    window = {key: repo[key] for key in WINDOW_KEYS if key in repo and repo[key] is not None}
    record = {
        "rank": repo.get("rank"),
        "full_name": full_name,
        "url": f"https://github.com/{full_name}" if full_name else None,
        "trendshift_url": (
            f"{BASE_URL}/repositories/{repository_id}" if repository_id is not None else None
        ),
        "description": _clean(repo.get("repository_description")),
        "language": _clean(repo.get("repository_language") or repo.get("language")),
        "stars": repo.get("repository_stars"),
        "forks": repo.get("repository_forks"),
        "stars_gained": repo.get("repository_stars_gained"),
        "forks_gained": repo.get("repository_forks_gained"),
        "score": repo.get("score"),
        "created_at": repo.get("repository_created_at"),
        "tags": tags,
        "mentioned_on": list(repo.get("social_mention_platforms") or []),
        "likes": repo.get("like_count"),
        "bookmarks": repo.get("bookmark_count"),
    }
    if window:
        record["window"] = window
    return record


def collect(period: str, timeout: float) -> dict[str, Any]:
    url = PERIODS[period]
    html = fetch_html(url, timeout)
    repos = repositories_from_flight(html)
    source = "page-data"
    if repos is None:
        repos = repositories_from_jsonld(html)
        source = "json-ld"
    if not repos:
        raise SystemExit(f"Nenhum repositório encontrado em {url}")

    return {
        "source": url,
        "extracted_from": source,
        "period": period,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "count": len(repos),
        "repositories": [normalize(repo) for repo in repos],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lista repositórios em tendência do Trendshift em JSON.")
    parser.add_argument(
        "--period",
        choices=tuple(PERIODS),
        default="today",
        help="janela do ranking (padrão: today)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="arquivo de saída. Sem este argumento, o JSON vai para a saída padrão.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="quantidade máxima de repositórios. 0 mantém a lista inteira.",
    )
    parser.add_argument("--timeout", type=float, default=30, help="timeout da requisição, em segundos")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.limit < 0:
        raise SystemExit("--limit precisa ser zero ou positivo")

    payload = collect(args.period, args.timeout)
    if args.limit:
        payload["repositories"] = payload["repositories"][: args.limit]
        payload["count"] = len(payload["repositories"])

    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
