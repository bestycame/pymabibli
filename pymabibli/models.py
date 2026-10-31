"""Data models for pymabibli."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Account:
    """The reader's account summary."""

    first_name: str
    last_name: str
    card_number: str
    subscription_end: date | None
    subscription_type: str | None


@dataclass(frozen=True)
class Message:
    """A status message the site shows after an action, e.g. a renewal."""

    level: str
    text: str


@dataclass(frozen=True)
class Loan:
    """A borrowed item."""

    title: str
    notice_id: str | None
    document_type: str | None
    authors: list[str]
    publisher: str | None
    library: str | None
    loan_date: date | None
    due_date: date | None
    renew_url: str | None
    # Public; redirects to the cover image, or a generic placeholder when there is none
    cover_url: str | None = None

    @property
    def renewable(self) -> bool:
        return self.renew_url is not None
