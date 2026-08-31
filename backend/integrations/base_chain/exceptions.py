class BaseChainError(Exception):
    pass


class BaseChainConnectionError(BaseChainError):
    pass


class BaseChainTransactionError(BaseChainError):
    pass


class BaseChainContractError(BaseChainError):
    pass
