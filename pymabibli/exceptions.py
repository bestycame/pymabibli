"""Exceptions for pymabibli."""


class MabibliError(Exception):
    """Base error."""


class MabibliConnectionError(MabibliError):
    """The site could not be reached or returned an unexpected response."""


class MabibliAuthError(MabibliError):
    """The card number or password was rejected."""


class MabibliRenewError(MabibliError):
    """The library refused to renew a loan."""
