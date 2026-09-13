"""Public failure categories: absence of a proof is never acceptance."""


class QKFError(ValueError):
    """Base exception for expected input and proof failures."""


class Unsupported(QKFError):
    """Input is outside the supported proof fragment."""


class ResourceLimit(Unsupported):
    """A documented complexity budget was exceeded."""


class InvalidCertificate(QKFError):
    """A certificate is malformed or does not prove the supplied source."""


class InvalidInput(QKFError):
    """The API or command was given an invalid argument."""
