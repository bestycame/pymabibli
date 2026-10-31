"""Parse the HTML pages of mabibli.be (Drupal + BGM modules)."""

from __future__ import annotations

from datetime import date, datetime
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

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


def is_logged_in(html: str) -> bool:
    return "/user/logout" in html


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


def parse_account(html: str) -> Account:
    soup = _soup(html)
    user = soup.select_one(".user--type-user")
    if user is None:
        raise ValueError("Account block not found")
    end = _text(user.select_one(".field--name-field-date-fin-d-abonnement .field__item"))
    return Account(
        first_name=_text(user.select_one(".field--name-field-prenom")) or "",
        last_name=_text(user.select_one(".field--name-field-nom")) or "",
        card_number=_text(user.select_one(".field--name-username")) or "",
        subscription_end=_parse_date(end),
        subscription_type=_text(user.select_one(".field--name-field-type-abonnement")),
    )


def parse_loans(html: str) -> list[Loan]:
    soup = _soup(html)
    loans: list[Loan] = []
    for pret in soup.select("div.pret"):
        item = pret.parent
        if not isinstance(item, Tag):
            continue
        title_link = item.select_one(".field--name-node-title a")
        notice_href = title_link.get("href") if title_link else None
        renew = pret.select_one("a.button__prolongation")
        renew_href = renew.get("href") if renew else None
        library = pret.select_one(".mediatheque div")
        loans.append(
            Loan(
                title=_clean_title(_text(title_link) or ""),
                notice_id=_notice_id(notice_href),
                document_type=_text(item.select_one(".typedoc")),
                authors=_unique(
                    _text(a)
                    for a in item.select(".field--name-field-auteurs .field__item")
                ),
                publisher=_text(item.select_one(".field--name-field-editeur .field__item")),
                library=_text(library),
                loan_date=_parse_date(_text(pret.select_one(".field--name-field-date-emprunt"))),
                due_date=_parse_date(_text(pret.select_one(".field--name-field-date-de-retour"))),
                renew_url=urljoin(BASE_URL, renew_href) if isinstance(renew_href, str) else None,
            )
        )
    return loans


def parse_next_page_url(html: str) -> str | None:
    """Return the "Suivant" link of a paged list, or None on the last page."""
    for link in _soup(html).select(".pager a[href]"):
        href = link.get("href")
        if "suivant" in link.get_text().lower() and isinstance(href, str):
            return urljoin(BASE_URL, href)
    return None


def parse_renew_all_url(html: str) -> str | None:
    link = _soup(html).select_one(".toutprolonger a.button__prolongation[href]")
    href = link.get("href") if link else None
    return urljoin(BASE_URL, href) if isinstance(href, str) else None


def parse_messages(html: str) -> list[Message]:
    messages: list[Message] = []
    for element in _soup(html).select(", ".join(f".{cls}" for cls in _MESSAGE_LEVELS)):
        classes = element.get("class") or []
        level = next(_MESSAGE_LEVELS[c] for c in classes if c in _MESSAGE_LEVELS)
        if text := _text(element):
            messages.append(Message(level, text))
    return messages


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
    title = re.sub(r"'\|\s*", "'", title)
    return re.sub(r"\s*\|\s*", " ", title).strip()


def _notice_id(href: object) -> str | None:
    if isinstance(href, str) and (match := re.search(r"/notice/(\d+)", href)):
        return match.group(1)
    return None


def _unique(values) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))
