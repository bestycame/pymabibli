# Mabibli Python Client
## NOT OFFICIALLY SUPPORTED BY THE PROVINCE DE LIÈGE --

An async Python client library for [mabibli.be](https://mabibli.be/), the library network of the Province of Liège.
This client logs in with your library card and reads your account, loans and borrowing history, and can renew loans.
Developped for a Home Assistant integration. At least for now.

## Installation
You can install the package using pip:

```bash
pip install pymabibli
```

## Usage

Here's a basic example of how to use the client:

```python
import asyncio

from pymabibli import MabibliClient


async def main():
    async with MabibliClient("your-card-number", "your-password") as client:
        # Log in (also done automatically by the other methods)
        await client.login()

        # Get account information
        account = await client.get_account()
        print(f"Membership ends: {account.subscription_end}")

        # Get current loans
        loans = await client.get_loans()
        for loan in loans:
            print(f"{loan.title} [{loan.library}] due {loan.due_date}")

        # Get borrowing history
        history = await client.get_history()
        print(f"{len(history)} items borrowed")

        # Renew one loan
        messages = await client.renew_loan(loans[0])

        # Renew all loans ("Tout prolonger")
        messages = await client.renew_all()


asyncio.run(main())
```

To reuse an existing `aiohttp.ClientSession` (as Home Assistant does), pass it with `session=`.
The client then leaves it open when closing.

## Error Handling

The client provides specific exception classes:

### Exception Classes

- `MabibliError`: Base exception for all errors
- `MabibliAuthError`: Raised when the card number or password is rejected
- `MabibliConnectionError`: Raised when the site can't be reached or returns an unexpected page
- `MabibliRenewError`: Raised when a loan can't be renewed or the site refuses the renewal

### Example Error Handling

```python
from pymabibli import MabibliAuthError, MabibliClient, MabibliRenewError

async def renew_everything():
    async with MabibliClient("your-card-number", "your-password") as client:
        try:
            loans = await client.get_loans()
        except MabibliAuthError as e:
            print(f"Login failed: {e}")
            return

        for loan in loans:
            if not loan.renewable:
                continue
            try:
                await client.renew_loan(loan)
            except MabibliRenewError as e:
                print(f"Could not renew {loan.title}: {e}")
```

### Authentication

mabibli.be authenticates through a CAS server (`centralcas.gminvent.fr`).
The client logs in on first use and logs in again when the site's session expires.

### API Methods

- `login() -> None`: Log in with the card number and password
- `get_account() -> Account`: Get name, card number and membership end date
- `get_loans() -> list[Loan]`: Get current loans, across all pages
- `get_history() -> list[Loan]`: Get previously borrowed items, newest first, across all pages
- `renew_loan(loan: Loan) -> list[Message]`: Renew one loan and return the site's messages
- `renew_all() -> list[Message]`: Renew all renewable loans and return the site's messages

## Development

```bash
pipenv install --dev
pipenv run pytest
pipenv run flake8
```

The scripts in `examples/` run against the real site with your own card.
`examples/renew.py` really renews a loan, after asking which one.

## License
This project is licensed under the MIT License - see the LICENSE file for details.
