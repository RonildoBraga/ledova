from integrations.abr.client import RegistryObservation

DECLARATION = {
    "declarant_name": "Synthetic Declarant",
    "board_resolution_reference": "Synthetic board resolution BR-001",
    "attest_officeholder": True,
}


def matching_observation(company):
    return RegistryObservation(
        acn=company.acn.replace(" ", ""),
        abn=company.abn.replace(" ", "") or "99123456780",
        entity_name=company.name,
        entity_type="PRV",
        entity_status="Active",
    )
