
from string import printable
from typing import Callable
from typing_extensions import TypeAlias

CharMapper: TypeAlias = Callable[[bytes], bytes]


def reverse_map(mapper: CharMapper) -> CharMapper:
    mapping_pairs = ((src, mapper(bytes([src]))[0]) for src in printable)
    revmapper = {im: src for src, im in mapping_pairs if im != src}
    def wrapper(seq):
        return bytes(revmapper.get(c, c) for c in seq)
    return wrapper


def hebrew_char_map(seq: bytes) -> bytes:
    return bytes(c + 0xA0 if ord('@') <= c <= ord('Z') else c for c in seq)


def identity_map(seq: bytes) -> bytes:
    return seq


def decrypt(msg: bytes, char_map: CharMapper, encoding: str) -> str:
    return char_map(msg).decode(encoding)
