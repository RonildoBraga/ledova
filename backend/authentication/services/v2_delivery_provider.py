from enum import Enum


class V2DeliveryProviderResult(Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"
