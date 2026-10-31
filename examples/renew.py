"""Renew one of your loans after confirmation: python examples/renew.py"""

import asyncio
import getpass
import os

from pymabibli import MabibliClient, MabibliRenewError


async def main() -> None:
    username = os.environ.get("MABIBLI_USERNAME") or input("Card number: ")
    password = os.environ.get("MABIBLI_PASSWORD") or getpass.getpass("Password: ")
    async with MabibliClient(username, password) as client:
        loans = [loan for loan in await client.get_loans() if loan.renewable]
        if not loans:
            print("No renewable loans")
            return
        for index, loan in enumerate(loans, 1):
            print(f"{index}. {loan.title} [{loan.library}] due {loan.due_date}")
        choice = input("Number to renew (empty to cancel): ").strip()
        if not choice:
            return
        loan = loans[int(choice) - 1]
        try:
            messages = await client.renew_loan(loan)
        except MabibliRenewError as err:
            print("Refused:", err)
        else:
            print("Messages:", messages or "(none shown)")
        for updated in await client.get_loans():
            if updated.notice_id == loan.notice_id:
                print(f"Due date now {updated.due_date} (was {loan.due_date})")


asyncio.run(main())
