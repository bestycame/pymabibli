"""Tests for the client, with page fetching stubbed out."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from pymabibli import MabibliClient, MabibliRenewError, Message

FIXTURES = Path(__file__).parent / "fixtures"
HISTORY_URL = "https://mabibli.be/page/user/mon-historique"
LOANS_URL = "https://mabibli.be/page/user/prets-en-cours"
RENEW_URL = "https://mabibli.be/bgm--prolongation--byId/1/He/2/L25vZGUvMQ=="
RENEW_ALL_URL = "https://mabibli.be/bgm--toutprolongation--byId/L25vZGUvMQ=="


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeSite:
    """Serve fixture pages by URL and record which URLs were fetched."""

    def __init__(self) -> None:
        self.pages: dict[str, str] = {}
        self.requested: list[str] = []

    async def get_text(self, url: str, **kwargs: object) -> str:
        self.requested.append(url)
        return self.pages[url]


@pytest.fixture
def site() -> FakeSite:
    return FakeSite()


@pytest_asyncio.fixture
async def client(site: FakeSite, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MabibliClient]:
    async with MabibliClient("041000000000", "secret") as client:
        # Skip the CAS login; it is covered by the live example script
        client.logged_in = True
        monkeypatch.setattr(client, "_get_text", site.get_text)
        yield client


@pytest.mark.asyncio
async def test_get_history_follows_pages(client: MabibliClient, site: FakeSite) -> None:
    site.pages[HISTORY_URL] = _fixture("history_page1.html")
    site.pages[f"{HISTORY_URL}?prh=1"] = _fixture("history_page2.html")

    loans = await client.get_history()

    assert [loan.title for loan in loans] == ["Premier livre", "Second livre"]
    assert site.requested == [HISTORY_URL, f"{HISTORY_URL}?prh=1"]


@pytest.mark.asyncio
async def test_renew_loan(client: MabibliClient, site: FakeSite) -> None:
    site.pages[LOANS_URL] = _fixture("loans.html")
    site.pages[RENEW_URL] = _fixture("renew_success.html")
    loan = (await client.get_loans())[0]

    assert await client.renew_loan(loan) == [Message("status", "Prolongation effectuée")]
    assert site.requested[-1] == RENEW_URL


@pytest.mark.asyncio
async def test_renew_loan_refused(client: MabibliClient, site: FakeSite) -> None:
    site.pages[LOANS_URL] = _fixture("loans.html")
    site.pages[RENEW_URL] = _fixture("renew_error.html")
    loan = (await client.get_loans())[0]

    with pytest.raises(MabibliRenewError, match="document réservé"):
        await client.renew_loan(loan)


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
