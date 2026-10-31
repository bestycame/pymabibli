"""Tests for the client, with page fetching stubbed out."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from pymabibli import MabibliAuthError, MabibliClient, MabibliRenewError, Message
from pymabibli.client import CAS_LOGIN_URL, SERVICE_URL

FIXTURES = Path(__file__).parent / "fixtures"
HISTORY_URL = "https://mabibli.be/page/user/mon-historique"
LOANS_URL = "https://mabibli.be/page/user/prets-en-cours"
RENEW_URL = "https://mabibli.be/bgm--prolongation--byId/1/He/2/L25vZGUvMQ=="
RENEW_ALL_URL = "https://mabibli.be/bgm--toutprolongation--byId/L25vZGUvMQ=="
LOGGED_OUT_PAGE = "<html><a href='/user/login'>Connexion</a></html>"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _history_page(next_href: str) -> str:
    return (
        "<a href='/user/logout'>X</a>"
        "<div class='field__item'><div class='notice'><div class='field--name-node-title'>"
        "<a href='/notice/1'>Livre</a></div></div><div class='pret'></div></div>"
        f"<div class='pager'><a href='{next_href}'>Suivant</a></div>"
    )


class FakeSite:
    """Serve fixture pages by URL, follow fake redirects, and record requests."""

    def __init__(self) -> None:
        self.pages: dict[str, str] = {}
        self.redirects: dict[str, str] = {}
        self.requested: list[str] = []

    async def fetch(self, url: str, **kwargs: object) -> tuple[str, str]:
        self.requested.append(url)
        final_url = self.redirects.get(url, url)
        return self.pages[final_url], final_url


@pytest.fixture
def site() -> FakeSite:
    return FakeSite()


@pytest_asyncio.fixture
async def client(site: FakeSite, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MabibliClient]:
    async with MabibliClient("041000000000", "secret") as client:
        # Skip the CAS login; it is covered by the live example script
        client.logged_in = True
        monkeypatch.setattr(client, "_fetch", site.fetch)
        yield client


def test_client_can_be_created_outside_event_loop() -> None:
    MabibliClient("041000000000", "secret")


@pytest.mark.asyncio
async def test_login_with_valid_cas_cookie(client: MabibliClient, site: FakeSite) -> None:
    client.logged_in = False
    site.redirects[CAS_LOGIN_URL] = SERVICE_URL
    site.pages[SERVICE_URL] = "<a href='/user/logout'>X</a>"

    await client.login()

    assert client.logged_in
    assert site.requested == [CAS_LOGIN_URL]


@pytest.mark.asyncio
async def test_get_history_follows_pages(client: MabibliClient, site: FakeSite) -> None:
    site.pages[HISTORY_URL] = _fixture("history_page1.html")
    site.pages[f"{HISTORY_URL}?prh=1"] = _fixture("history_page2.html")

    loans = await client.get_history()

    assert [loan.title for loan in loans] == ["Premier livre", "Second livre"]
    assert site.requested == [HISTORY_URL, f"{HISTORY_URL}?prh=1"]


@pytest.mark.asyncio
async def test_get_history_resolves_relative_pager_link(client: MabibliClient, site: FakeSite) -> None:
    site.pages[HISTORY_URL] = _history_page("?prh=1")
    site.pages[f"{HISTORY_URL}?prh=1"] = _fixture("history_page2.html")

    await client.get_history()

    assert site.requested == [HISTORY_URL, f"{HISTORY_URL}?prh=1"]


@pytest.mark.asyncio
async def test_get_history_stops_on_repeated_page(client: MabibliClient, site: FakeSite) -> None:
    site.pages[HISTORY_URL] = _history_page("/page/user/mon-historique")

    loans = await client.get_history()

    assert len(loans) == 1
    assert site.requested == [HISTORY_URL]


@pytest.mark.asyncio
async def test_renew_loan(client: MabibliClient, site: FakeSite) -> None:
    site.pages[LOANS_URL] = _fixture("loans.html")
    site.pages[RENEW_URL] = _fixture("renew_success.html")
    loan = (await client.get_loans())[0]

    assert await client.renew_loan(loan) == [Message("status", "Prolongation effectuée")]
    assert site.requested[-2:] == [LOANS_URL, RENEW_URL]


@pytest.mark.asyncio
async def test_renew_loan_refused(client: MabibliClient, site: FakeSite) -> None:
    site.pages[LOANS_URL] = _fixture("loans.html")
    site.pages[RENEW_URL] = _fixture("renew_error.html")
    loan = (await client.get_loans())[0]

    with pytest.raises(MabibliRenewError, match="document réservé"):
        await client.renew_loan(loan)


@pytest.mark.asyncio
async def test_renew_loan_is_not_retried(client: MabibliClient, site: FakeSite) -> None:
    site.pages[LOANS_URL] = _fixture("loans.html")
    site.pages[RENEW_URL] = LOGGED_OUT_PAGE
    loan = (await client.get_loans())[0]

    with pytest.raises(MabibliAuthError, match="check the loan"):
        await client.renew_loan(loan)

    assert site.requested.count(RENEW_URL) == 1
    assert not client.logged_in


@pytest.mark.asyncio
async def test_renew_loan_not_renewable(client: MabibliClient, site: FakeSite) -> None:
    site.pages[LOANS_URL] = _fixture("loans.html")
    loan = (await client.get_loans())[1]

    with pytest.raises(MabibliRenewError, match="cannot be renewed"):
        await client.renew_loan(loan)


@pytest.mark.asyncio
async def test_renew_all(client: MabibliClient, site: FakeSite) -> None:
    site.pages[LOANS_URL] = _fixture("loans.html")
    site.pages[RENEW_ALL_URL] = _fixture("renew_success.html")

    assert await client.renew_all() == [Message("status", "Prolongation effectuée")]
    assert site.requested == [LOANS_URL, RENEW_ALL_URL]
