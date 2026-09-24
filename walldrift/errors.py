class WalldriftError(Exception):
    """An expected failure, reported to the user as a one-line message."""


class ConfigError(WalldriftError):
    """The config or secrets file is invalid."""


class HttpError(WalldriftError):
    """A request failed after all retries."""


class SetterError(WalldriftError):
    """The wallpaper could not be set."""
