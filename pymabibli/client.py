"""Client for mabibli.be, which authenticates through the GMInvent CAS server."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Self
from urllib.parse import urljoin

import aiohttp

from .exceptions import MabibliAuthError, MabibliConnectionError, MabibliRenewError
from .models import Account, Loan, Message
from .parsers import (
    is_logged_in,
    parse_account,
    parse_loans,
    parse_messages,
    parse_next_page_url,
    parse_renew_all_url,
)

BASE_URL = "https://mabibli.be"
ACCOUNT_PATH = "/user"
LOANS_PATH = "/page/user/prets-en-cours"
HISTORY_PATH = "/page/user/mon-historique"
MAX_PAGES = 100
CAS_LOGIN_URL = "https://centralcas.gminvent.fr/cas/login"
SERVICE_URL = f"{BASE_URL}/casservice"
DEFAULT_SILO = "Chirx"


class _FormParser(HTMLParser):
    """Collect the input fields of the CAS login form."""

    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}
        self.has_error = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name"):
            self.fields[attributes["name"]] = attributes.get("value") or ""
        # Apereo CAS renders failed logins in an element with id "loginErrorsPanel"
        if attributes.get("id") == "loginErrorsPanel":
            self.has_error = True


class MabibliClient:
    """Log in to mabibli.be and keep the authenticated session."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        silo: str = DEFAULT_SILO,
    ) -> None:
        self._username = username
        self._password = password
        self._silo = silo
        self._session = session or aiohttp.ClientSession()
        self._close_session = session is None
        self.logged_in = False

    async def login(self) -> None:
        """Authenticate against CAS and land on mabibli.be with a session cookie."""
        params = {
            "fromDrupalBGM": "Non",
            "fromDrupalSilo": self._silo,
            "service": SERVICE_URL,
        }
        page = await self._get_text(CAS_LOGIN_URL, params=params)
        form = _FormParser()
        form.feed(page)
        if "execution" not in form.fields:
            raise MabibliConnectionError("CAS login form not found")

        data = {
            "username": self._username,
            "password": self._password,
            "customFields[silo]": self._silo,
            "execution": form.fields["execution"],
            "_eventId": "submit",
            "geolocation": "",
        }
        try:
            async with self._session.post(
                CAS_LOGIN_URL, params=params, data=data
            ) as response:
                body = await response.text()
                final_url = response.url
        except aiohttp.ClientError as err:
            raise MabibliConnectionError(err) from err

        # On success CAS redirects to the service with a ticket, which mabibli.be
        # exchanges for its own session cookie.
        if final_url.host == "centralcas.gminvent.fr":
            result = _FormParser()
            result.feed(body)
            if result.has_error or response.status == 401:
                raise MabibliAuthError("Invalid card number or password")
            raise MabibliConnectionError(f"Login did not redirect (HTTP {response.status})")
        self.logged_in = True

    async def get_account(self) -> Account:
        """Return the reader's name, card number and membership end date."""
        return parse_account(await self._get_authenticated(ACCOUNT_PATH))

    async def get_loans(self) -> list[Loan]:
        """Return the items currently on loan, across all pages."""
        return await self._get_paged_loans(LOANS_PATH)

    async def get_history(self) -> list[Loan]:
        """Return previously borrowed items, newest first, across all pages."""
        return await self._get_paged_loans(HISTORY_PATH)

    async def renew_loan(self, loan: Loan) -> list[Message]:
        """Renew one loan and return the messages the site showed.

        Raises MabibliRenewError if the site reports an error.
        """
        if loan.renew_url is None:
            raise MabibliRenewError(f"{loan.title} cannot be renewed")
        return await self._renew(loan.renew_url)

    async def renew_all(self) -> list[Message]:
        """Renew every renewable loan, like the "Tout prolonger" button."""
        url = parse_renew_all_url(await self._get_authenticated(LOANS_PATH))
        if url is None:
            raise MabibliRenewError("No loans can be renewed")
        return await self._renew(url)

    async def _renew(self, url: str) -> list[Message]:
        messages = parse_messages(await self._get_authenticated(url))
        if errors := [m.text for m in messages if m.level == "error"]:
            raise MabibliRenewError("; ".join(errors))
        return messages

    async def _get_paged_loans(self, path: str) -> list[Loan]:
        loans: list[Loan] = []
        url: str | None = path
        for _ in range(MAX_PAGES):
            if url is None:
                break
            html = await self._get_authenticated(url)
            loans.extend(parse_loans(html))
            url = parse_next_page_url(html)
        return loans

    async def _get_authenticated(self, url: str) -> str:
        """Fetch a page, logging in first or again if the Drupal session expired."""
        url = urljoin(BASE_URL, url)
        if not self.logged_in:
            await self.login()
        html = await self._get_text(url)
        if is_logged_in(html):
            return html
        self.logged_in = False
        await self.login()
        html = await self._get_text(url)
        if not is_logged_in(html):
            raise MabibliAuthError("Session not accepted after login")
        return html

    async def _get_text(self, url: str, **kwargs) -> str:
        try:
            async with self._session.get(url, **kwargs) as response:
                response.raise_for_status()
                return await response.text()
        except aiohttp.ClientError as err:
            raise MabibliConnectionError(err) from err

    async def close(self) -> None:
        if self._close_session:
            await self._session.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()
