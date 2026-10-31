"""Client for mabibli.be, which authenticates through the GMInvent CAS server."""

from __future__ import annotations

from html.parser import HTMLParser
import logging
from typing import Self
from urllib.parse import urljoin, urlsplit

import aiohttp

from .exceptions import MabibliAuthError, MabibliConnectionError, MabibliRenewError
from .models import Account, Loan, Message
from .parsers import (
    BASE_URL,
    is_logged_in,
    parse_account,
    parse_loans_page,
    parse_messages,
    parse_renew_all_url,
)

_LOGGER = logging.getLogger(__name__)

ACCOUNT_PATH = "/user"
LOANS_PATH = "/page/user/prets-en-cours"
HISTORY_PATH = "/page/user/mon-historique"
MAX_PAGES = 100
CAS_HOST = "centralcas.gminvent.fr"
CAS_LOGIN_URL = f"https://{CAS_HOST}/cas/login"
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
    """Log in to mabibli.be and keep the authenticated session.

    The login lives in the session's cookie jar, so a session passed in must be
    dedicated to this client: sharing one between two cards mixes their accounts.
    """

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
        self._session = session
        self._close_session = session is None
        self.logged_in = False

    async def login(self) -> None:
        """Authenticate against CAS and land on mabibli.be with a session cookie."""
        params = {
            "fromDrupalBGM": "Non",
            "fromDrupalSilo": self._silo,
            "service": SERVICE_URL,
        }
        page, page_url = await self._fetch(CAS_LOGIN_URL, params=params)
        # A still valid CAS cookie skips the form and redirects straight to the service
        if urlsplit(page_url).hostname != CAS_HOST:
            self.logged_in = True
            return
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
            async with self._get_session().post(
                CAS_LOGIN_URL, params=params, data=data
            ) as response:
                body = await response.text()
                final_url = response.url
                status = response.status
        except aiohttp.ClientError as err:
            raise MabibliConnectionError(err) from err

        # On success CAS redirects to the service with a ticket, which mabibli.be
        # exchanges for its own session cookie.
        if final_url.host == CAS_HOST:
            result = _FormParser()
            result.feed(body)
            if result.has_error or status == 401:
                raise MabibliAuthError("Invalid card number or password")
            raise MabibliConnectionError(f"Login did not redirect (HTTP {status})")
        self.logged_in = True

    async def get_account(self) -> Account:
        """Return the reader's name, card number and membership end date."""
        html, _ = await self._get_authenticated(ACCOUNT_PATH)
        return parse_account(html)

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
        # Make sure the session is valid first, so the renewal is sent exactly once
        await self._get_authenticated(LOANS_PATH)
        return await self._send_renewal(loan.renew_url)

    async def renew_all(self) -> list[Message]:
        """Renew every renewable loan, like the "Tout prolonger" button."""
        html, page_url = await self._get_authenticated(LOANS_PATH)
        url = parse_renew_all_url(html, page_url)
        if url is None:
            raise MabibliRenewError("No loans can be renewed")
        return await self._send_renewal(url)

    async def _send_renewal(self, url: str) -> list[Message]:
        # Renewal links are state-changing GETs, so they are never retried
        html, _ = await self._fetch(url)
        if not is_logged_in(html):
            self.logged_in = False
            raise MabibliAuthError("Session lost while renewing; check the loan before retrying")
        messages = parse_messages(html)
        if errors := [m.text for m in messages if m.level == "error"]:
            raise MabibliRenewError("; ".join(errors))
        return messages

    async def _get_paged_loans(self, path: str) -> list[Loan]:
        loans: list[Loan] = []
        url = path
        visited: set[str] = set()
        for _ in range(MAX_PAGES):
            html, page_url = await self._get_authenticated(url)
            visited.add(page_url)
            page_loans, next_url = parse_loans_page(html, page_url)
            loans.extend(page_loans)
            if next_url is None or next_url in visited:
                return loans
            url = next_url
        _LOGGER.warning("Stopped after %s pages of %s; the list is incomplete", MAX_PAGES, path)
        return loans

    async def _get_authenticated(self, url: str) -> tuple[str, str]:
        """Fetch a page, logging in first or again if the Drupal session expired."""
        url = urljoin(BASE_URL, url)
        if not self.logged_in:
            await self.login()
        html, final_url = await self._fetch(url)
        if is_logged_in(html):
            return html, final_url
        self.logged_in = False
        await self.login()
        html, final_url = await self._fetch(url)
        if not is_logged_in(html):
            raise MabibliAuthError("Session not accepted after login")
        return html, final_url

    async def _fetch(self, url: str, **kwargs) -> tuple[str, str]:
        """Return the body and the final URL after redirects."""
        try:
            async with self._get_session().get(urljoin(BASE_URL, url), **kwargs) as response:
                response.raise_for_status()
                return await response.text(), str(response.url)
        except aiohttp.ClientError as err:
            raise MabibliConnectionError(err) from err

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._close_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()
