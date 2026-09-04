class TransakError(Exception):
    pass


class TransakConfigurationError(TransakError):
    pass


class TransakApiError(TransakError):
    pass
