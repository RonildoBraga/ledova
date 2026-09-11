import hashlib
import re
from dataclasses import dataclass, replace

import base58
import bech32

MAX_MONEY = 21_000_000 * 100_000_000
MAX_TRANSACTION_BYTES = 400_000
MAX_ELEMENTS = 1000


@dataclass(frozen=True)
class BitcoinInput:
    tx_hash: str
    output_index: int
    script: bytes
    sequence: int
    witness: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class BitcoinOutput:
    satoshis: int
    script: bytes


@dataclass(frozen=True)
class BitcoinTransaction:
    raw: bytes
    tx_hash: str
    witness_hash: str
    version: int
    lock_time: int
    inputs: tuple[BitcoinInput, ...]
    outputs: tuple[BitcoinOutput, ...]


class _Reader:
    def __init__(self, raw):
        self.raw = raw
        self.offset = 0

    def read(self, size):
        if size < 0 or self.offset + size > len(self.raw):
            raise ValueError("Truncated Bitcoin transaction.")
        value = self.raw[self.offset : self.offset + size]
        self.offset += size
        return value

    def integer(self, size):
        return int.from_bytes(self.read(size), "little")

    def compact(self, maximum):
        tag = self.integer(1)
        if tag < 253:
            value = tag
        else:
            width = {253: 2, 254: 4, 255: 8}[tag]
            value = self.integer(width)
            if value < {253: 253, 254: 65536, 255: 4294967296}[tag]:
                raise ValueError("Noncanonical Bitcoin vector length.")
        if value > maximum:
            raise ValueError("Bitcoin vector exceeds the supported size.")
        return value

    def script(self):
        return self.read(self.compact(10_000))


def _hash(raw):
    return hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex()


def decode_bitcoin_transaction(value):
    if isinstance(value, str):
        if len(value) > MAX_TRANSACTION_BYTES * 2 or not re.fullmatch(r"(?:[0-9a-fA-F]{2})+", value):
            raise ValueError("Invalid Bitcoin transaction hexadecimal bytes.")
        raw = bytes.fromhex(value)
    elif isinstance(value, bytes):
        raw = value
    else:
        raise ValueError("Bitcoin transaction bytes are required.")
    if not 10 <= len(raw) <= MAX_TRANSACTION_BYTES:
        raise ValueError("Bitcoin transaction size is unsupported.")
    reader = _Reader(raw)
    version = reader.integer(4)
    if not 1 <= version < 2**31:
        raise ValueError("Bitcoin transaction version is unsupported.")
    witness = raw[reader.offset] == 0
    if witness and reader.read(2) != b"\x00\x01":
        raise ValueError("Bitcoin witness flags are unsupported.")
    inputs_start = reader.offset
    count = reader.compact(MAX_ELEMENTS)
    if not count:
        raise ValueError("A Bitcoin transfer requires inputs.")
    inputs = []
    for _ in range(count):
        previous = reader.read(32)[::-1].hex()
        index = reader.integer(4)
        if previous == "00" * 32:
            raise ValueError("Coinbase inputs cannot be submitted as wallet transfers.")
        inputs.append(BitcoinInput(previous, index, reader.script(), reader.integer(4)))
    if len({(item.tx_hash, item.output_index) for item in inputs}) != len(inputs):
        raise ValueError("A Bitcoin transfer cannot spend an input twice.")
    count = reader.compact(MAX_ELEMENTS)
    if not count:
        raise ValueError("A Bitcoin transfer requires outputs.")
    outputs = []
    for _ in range(count):
        amount = reader.integer(8)
        if amount > MAX_MONEY:
            raise ValueError("A Bitcoin output exceeds the money supply.")
        outputs.append(BitcoinOutput(amount, reader.script()))
    if sum(item.satoshis for item in outputs) > MAX_MONEY:
        raise ValueError("Bitcoin outputs exceed the money supply.")
    outputs_end = reader.offset
    if witness:
        for index, item in enumerate(inputs):
            stack = tuple(reader.script() for _ in range(reader.compact(MAX_ELEMENTS)))
            inputs[index] = replace(item, witness=stack)
        if not any(item.witness for item in inputs):
            raise ValueError("An empty Bitcoin witness must use legacy serialization.")
    lock_time = reader.integer(4)
    if reader.offset != len(raw):
        raise ValueError("Unexpected trailing Bitcoin transaction bytes.")
    stripped = raw[:4] + raw[inputs_start:outputs_end] + raw[-4:]
    return BitcoinTransaction(raw, _hash(stripped), _hash(raw), version, lock_time, tuple(inputs), tuple(outputs))


def script_for_bitcoin_address(address, network):
    if network not in ("test", "regtest") or not isinstance(address, str):
        raise ValueError("An approved Bitcoin test network and address are required.")
    hrp, words = bech32.bech32_decode(address)
    if hrp is not None:
        program = bech32.convertbits(words[1:], 5, 8, False) if words and words[0] == 0 else None
        if hrp != {"test": "tb", "regtest": "bcrt"}[network] or program is None or len(program) not in (20, 32):
            raise ValueError("Unsupported Bitcoin test witness address.")
        return bytes([0, len(program), *program])
    try:
        payload = base58.b58decode_check(address)
    except (ValueError, TypeError):
        raise ValueError("Invalid Bitcoin test address.") from None
    if len(payload) == 21 and payload[0] == 111:
        return b"\x76\xa9\x14" + payload[1:] + b"\x88\xac"
    if len(payload) == 21 and payload[0] == 196:
        return b"\xa9\x14" + payload[1:] + b"\x87"
    raise ValueError("Unsupported Bitcoin test address.")


def bitcoin_address_for_script(script, network):
    if network not in ("test", "regtest"):
        raise ValueError("An approved Bitcoin test network is required.")
    if len(script) in (22, 34) and script[:2] == bytes([0, len(script) - 2]):
        hrp = {"test": "tb", "regtest": "bcrt"}[network]
        return bech32.bech32_encode(hrp, [0, *bech32.convertbits(script[2:], 8, 5, True)])
    if len(script) == 25 and script[:3] == b"\x76\xa9\x14" and script[-2:] == b"\x88\xac":
        return base58.b58encode_check(bytes([111]) + script[3:-2]).decode("ascii")
    if len(script) == 23 and script[:2] == b"\xa9\x14" and script[-1:] == b"\x87":
        return base58.b58encode_check(bytes([196]) + script[2:-1]).decode("ascii")
    raise ValueError("Unsupported Bitcoin transfer output script.")
