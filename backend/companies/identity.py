import unicodedata

from companies.validators import digits_of


def registered_name(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def company_identity(company):
    return {
        "name": registered_name(company.name),
        "acn": digits_of(company.acn),
        "abn": digits_of(company.abn),
        "company_type": company.company_type,
    }


def officeholder_declaration(company):
    return {
        "identity": company_identity(company),
        "declarant_name": company.declarant_name,
        "board_resolution_reference": company.board_resolution_reference,
    }
