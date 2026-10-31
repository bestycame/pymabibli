"""Parse the HTML pages of mabibli.be (Drupal + BGM modules)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .exceptions import MabibliConnectionError
from .models import Account, Loan, Message

BASE_URL = "https://mabibli.be"
_DATE_RE = re.compile(r"(\d{2})[-/](\d{2})[-/](\d{4})")
# The theme uses Bootstrap alerts; core Drupal markup is kept as a fallback
_MESSAGE_LEVELS = {
    "alert-danger": "error",
    "messages--error": "error",
    "alert-warning": "warning",
    "messages--warning": "warning",
    "alert-success": "status",
    "alert-info": "status",
    "messages--status": "status",
}
_MESSAGE_SELECTOR = ", ".join(f".{cls}" for cls in _MESSAGE_LEVELS)


def is_logged_in(html: str) -> bool:
    return "/user/logout" in html


def parse_account(html: str) -> Account:
    user = _soup(html).select_one(".user--type-user")
    if user is None:
        raise MabibliConnectionError("Account block not found")
    end = _text(user.select_one(".field--name-field-date-fin-d-abonnement .field__item"))
    return Account(
        first_name=_text(user.select_one(".field--name-field-prenom")) or "",
        last_name=_text(user.select_one(".field--name-field-nom")) or "",
        card_number=_text(user.select_one(".field--name-username")) or "",
        subscription_end=_parse_date(end),
        subscription_type=_text(user.select_one(".field--name-field-type-abonnement")),
    )


def parse_loans_page(html: str, page_url: str = BASE_URL) -> tuple[list[Loan], str | None]:
    """Return the loans on a page and the URL of the next page, if any."""
    soup = _soup(html)
    return _loans(soup, page_url), _next_page_url(soup, page_url)


def parse_loans(html: str, page_url: str = BASE_URL) -> list[Loan]:
    return _loans(_soup(html), page_url)


def parse_next_page_url(html: str, page_url: str = BASE_URL) -> str | None:
    """Return the "Suivant" link of a paged list, or None on the last page."""
    return _next_page_url(_soup(html), page_url)


def parse_renew_all_url(html: str, page_url: str = BASE_URL) -> str | None:
    link = _soup(html).select_one(".toutprolonger a.button__prolongation[href]")
    return _absolute(link.get("href") if link else None, page_url)


def parse_messages(html: str) -> list[Message]:
    soup = _soup(html)
    containers = soup.select("[data-drupal-messages], .messages__wrapper") or [soup]
    messages: list[Message] = []
    seen: set[int] = set()
    for container in containers:
        for element in container.select(_MESSAGE_SELECTOR):
            # A wrapper and its inner alert can both carry a message class
            if id(element) in seen or _has_message_ancestor(element, container):
                continue
            seen.add(id(element))
            level = next(_MESSAGE_LEVELS[c] for c in element.get("class") or [] if c in _MESSAGE_LEVELS)
            if text := _text(element):
                messages.append(Message(level, text))
    return messages


def _soup(html: str) -> BeautifulSoup:
    """Parse a page, including the blocks Drupal BigPipe streams as JSON scripts."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select("script[data-big-pipe-replacement-for-placeholder-with-id]"):
        try:
            commands = json.loads(script.string or "")
        except ValueError:
            continue
        for command in commands:
            if command.get("command") == "insert" and command.get("data"):
                script.insert_before(BeautifulSoup(command["data"], "html.parser"))
        script.decompose()
    return soup


def _loans(soup: BeautifulSoup, page_url: str) -> list[Loan]:
    loans: list[Loan] = []
    for pret in soup.select("div.pret"):
        item = pret.parent
        if not isinstance(item, Tag):
            continue
        title_link = item.select_one(".field--name-node-title a")
        renew = pret.select_one("a.button__prolongation")
        cover = item.select_one(".field--name-field-couverture img[src]")
        loans.append(
            Loan(
                title=_clean_title(_text(title_link) or ""),
                notice_id=_notice_id(title_link.get("href") if title_link else None),
                document_type=_text(item.select_one(".typedoc")),
                authors=_unique(
                    _text(a)
                    for a in item.select(".field--name-field-auteurs .field__item")
                ),
                publisher=_text(item.select_one(".field--name-field-editeur .field__item")),
                library=_text(pret.select_one(".mediatheque div")),
                loan_date=_parse_date(_text(pret.select_one(".field--name-field-date-emprunt"))),
                due_date=_parse_date(_text(pret.select_one(".field--name-field-date-de-retour"))),
                renew_url=_absolute(renew.get("href") if renew else None, page_url),
                cover_url=_absolute(cover.get("src") if cover else None, page_url),
            )
        )
    return loans


def _next_page_url(soup: BeautifulSoup, page_url: str) -> str | None:
    for link in soup.select(".pager a[href]"):
        if "suivant" in link.get_text().lower():
            return _absolute(link.get("href"), page_url)
    return None


def _has_message_ancestor(element: Tag, container: Tag) -> bool:
    for parent in element.parents:
        if parent is container:
            return False
        if any(c in _MESSAGE_LEVELS for c in parent.get("class") or []):
            return True
    return False


def _absolute(href: object, page_url: str) -> str | None:
    return urljoin(page_url, href) if isinstance(href, str) else None


def _text(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    return " ".join(tag.get_text(" ").split()) or None


def _parse_date(value: str | None) -> date | None:
    if not value or not (match := _DATE_RE.search(value)):
        return None
    day, month, year = match.groups()
    return datetime(int(year), int(month), int(day)).date()


def _clean_title(title: str) -> str:
    # The catalogue marks the leading article with "|", e.g. "L'| Atelier"
    title = re.sub(r"(['’])\|\s*", r"\1", title)
    return re.sub(r"\s*\|\s*", " ", title).strip()


def _notice_id(href: object) -> str | None:
    if isinstance(href, str) and (match := re.search(r"/notice/(\d+)", href)):
        return match.group(1)
    return None


def _unique(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(v for v in values if v))
