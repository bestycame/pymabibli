"""Tests for the HTML parsers."""

from datetime import date
from pathlib import Path

import pytest

from pymabibli import MabibliError
from pymabibli.models import Message
from pymabibli.parsers import (
    is_logged_in,
    parse_account,
    parse_loans,
    parse_messages,
    parse_next_page_url,
    parse_renew_all_url,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_account() -> None:
    account = parse_account(_fixture("account.html"))
    assert account.first_name == "Jeanne"
    assert account.last_name == "DUPONT"
    assert account.card_number == "041000000000"
    assert account.subscription_end == date(2027, 3, 1)
    assert account.subscription_type == "03 - Adulte (03)"


def test_parse_account_unexpected_page() -> None:
    with pytest.raises(MabibliError, match="Account block not found"):
        parse_account("<html><a href='/user/logout'>X</a></html>")


def test_parse_loans() -> None:
    first, second = parse_loans(_fixture("loans.html"))

    assert first.title == "L'Atelier des petits artistes"
    assert first.notice_id == "111"
    assert first.document_type == "Livre"
    assert first.authors == ("Wilkes, Angela (1952-....)", "Doe, John Illustrateur")
    assert first.publisher == "Larousse"
    assert first.library == "Geer"
    assert first.loan_date == date(2026, 9, 20)
    assert first.due_date == date(2026, 11, 22)
    assert first.renew_url == "https://mabibli.be/bgm--prolongation--byId/1/He/2/L25vZGUvMQ=="
    assert first.cover_url == "https://mabibli.be/bgm--couverture/1"

    assert second.title == "Le Grand voyage"
    assert second.document_type == "DVD"
    assert second.authors == ()
    assert second.publisher is None
    assert second.due_date == date(2026, 11, 5)
    assert not second.renewable
    assert second.cover_url is None

    assert len({first, second}) == 2


def test_parse_loans_resolves_against_page_url() -> None:
    html = (
        "<div class='field__item'><div class='field--name-field-couverture'><img src='cover/1'></div>"
        "<div class='pret'><div class='prolongation'>"
        "<a class='button__prolongation' href='../renew/1'>Prolonger</a></div></div></div>"
    )
    (loan,) = parse_loans(html, "https://mabibli.be/page/user/prets-en-cours")
    assert loan.renew_url == "https://mabibli.be/page/renew/1"
    assert loan.cover_url == "https://mabibli.be/page/user/cover/1"


def test_clean_title_with_typographic_apostrophe() -> None:
    html = (
        "<div class='field__item'><div class='field--name-node-title'><a>L’| Été</a></div>"
        "<div class='pret'></div></div>"
    )
    assert parse_loans(html)[0].title == "L’Été"


def test_parse_loans_from_bigpipe() -> None:
    (loan,) = parse_loans(_fixture("loans_bigpipe.html"))
    assert loan.title == "L'Atelier des petits artistes"
    assert loan.library == "Geer"
    assert loan.due_date == date(2026, 11, 22)
    assert loan.renewable


def test_parse_next_page_url() -> None:
    assert (
        parse_next_page_url(_fixture("history_page1.html"))
        == "https://mabibli.be/page/user/mon-historique?prh=1"
    )
    assert parse_next_page_url(_fixture("history_page2.html")) is None


def test_parse_renew_all_url() -> None:
    assert (
        parse_renew_all_url(_fixture("loans.html"))
        == "https://mabibli.be/bgm--toutprolongation--byId/L25vZGUvMQ=="
    )
    assert parse_renew_all_url(_fixture("history_page1.html")) is None


def test_parse_messages() -> None:
    assert parse_messages(_fixture("renew_success.html")) == [
        Message("status", "Prolongation effectuée")
    ]
    assert parse_messages(_fixture("renew_error.html")) == [
        Message("error", "Prolongation impossible : document réservé")
    ]
    assert parse_messages(_fixture("loans.html")) == []


def test_parse_messages_ignores_alerts_outside_message_area() -> None:
    html = (
        "<div class='alert alert-danger'>Retard sur un document</div>"
        "<div data-drupal-messages><div class='messages messages--error'>"
        "<div class='alert alert-danger'>Prolongation impossible</div></div></div>"
    )
    assert parse_messages(html) == [Message("error", "Prolongation impossible")]


def test_is_logged_in() -> None:
    assert is_logged_in(_fixture("loans.html"))
    assert not is_logged_in("<html><a href='/user/login'>Connexion</a></html>")
