import rlp
from eth_keys.constants import SECPK1_N


def with_signature_s(raw, s, flip_parity=False):
    typed = raw[0] <= 0x7F
    fields = rlp.decode(raw[1:] if typed else raw)
    fields[-1] = s.to_bytes((s.bit_length() + 7) // 8, "big")
    if flip_parity:
        parity = int.from_bytes(fields[-3], "big")
        parity = parity ^ 1 if typed else parity + (1 if parity % 2 else -1)
        fields[-3] = parity.to_bytes((parity.bit_length() + 7) // 8, "big")
    return (raw[:1] if typed else b"") + rlp.encode(fields)


def high_s_transaction(raw):
    fields = rlp.decode(raw[1:] if raw[0] <= 0x7F else raw)
    return with_signature_s(raw, SECPK1_N - int.from_bytes(fields[-1], "big"), flip_parity=True)
