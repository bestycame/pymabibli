"""Try the client with your own card: python examples/try_login.py"""

import asyncio
import getpass
import os

from pymabibli import MabibliClient


async def main() -> None:
    username = os.environ.get("MABIBLI_USERNAME") or input("Card number: ")
    password = os.environ.get("MABIBLI_PASSWORD") or getpass.getpass("Password: ")
    async with MabibliClient(username, password) as client:
        account = await client.get_account()
        print(f"{account.first_name} {account.last_name}, card {account.card_number}")
        print(f"Membership ends {account.subscription_end} ({account.subscription_type})")
        for loan in await client.get_loans():
            print(f"- {loan.title} [{loan.library}] due {loan.due_date}, renewable: {loan.renewable}")
        history = await client.get_history()
        print(f"History: {len(history)} items, oldest borrowed {history[-1].loan_date if history else None}")


asyncio.run(main())
