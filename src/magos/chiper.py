from string import printable
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping
    from typing import TypeAlias

CharMapper: 'TypeAlias' = 'Callable[[bytes], bytes]'


class EncodeSettings(TypedDict):
    encoding: str
    errors: str


decrypts: dict[str, tuple[CharMapper, EncodeSettings]] = {}


RAW_BYTE_ENCODING = EncodeSettings(encoding='ascii', errors='surrogateescape')


def encode(inst: str, encoding: str = 'utf-8', errors: str = 'strict') -> bytes:
    return inst.encode(encoding=encoding, errors=errors)


def register(
    mapping: 'MutableMapping[str, tuple[CharMapper, EncodeSettings]]',
    code: str,
    encoding: str,
) -> 'Callable[[CharMapper], CharMapper]':
    def wrapper(mapper: CharMapper) -> CharMapper:
        mapping[code] = (mapper, EncodeSettings(encoding=encoding, errors='strict'))
        return mapper

    return wrapper


def reverse_map(mapper: CharMapper) -> CharMapper:
    mapping_pairs = (
        (src, mapper(bytes([src]))[0]) for src in printable.encode('ascii')
    )
    revmapper = {im: src for src, im in mapping_pairs if im != src}

    def wrapper(seq: bytes) -> bytes:
        return bytes(revmapper.get(c, c) for c in seq)

    return wrapper


@register(decrypts, 'he', 'windows-1255')
def hebrew_char_map(seq: bytes) -> bytes:
    return bytes(c + 0xA0 if ord('@') <= c <= ord('Z') else c for c in seq)


@register(decrypts, 'de', 'windows-1252')
def german_char_map(seq: bytes) -> bytes:
    raw = encode('#$+/;<=>', encoding='ascii')
    transformed = encode('äößÄÖÜüé', encoding='windows-1252')
    assert len(transformed) == len(set(transformed))
    tf = dict(zip(raw, transformed, strict=True))
    return bytes(tf.get(c, c) for c in seq)


@register(decrypts, 'es', 'windows-1252')
def spanish_char_map(seq: bytes) -> bytes:
    raw = encode('/;<=>@^_`', encoding='ascii')
    transformed = encode('éàíóúñ¿¡ü', encoding='windows-1252')
    assert len(transformed) == len(set(transformed))
    tf = dict(zip(raw, transformed, strict=True))
    return bytes(tf.get(c, c) for c in seq)


@register(decrypts, 'fr', 'windows-1252')
def french_char_map(seq: bytes) -> bytes:
    raw = encode('#$+/;<=>@^_`', encoding='ascii')
    transformed = encode('ôâÇéàûèêîçïù', encoding='windows-1252')
    assert len(transformed) == len(set(transformed))
    tf = dict(zip(raw, transformed, strict=True))
    return bytes(tf.get(c, c) for c in seq)


@register(decrypts, 'it', 'windows-1252')
def italian_char_map(seq: bytes) -> bytes:
    raw = encode('+/;<=`', encoding='ascii')
    transformed = encode('ìéàòèù', encoding='windows-1252')
    assert len(transformed) == len(set(transformed))
    tf = dict(zip(raw, transformed, strict=True))
    return bytes(tf.get(c, c) for c in seq)


@register(decrypts, 'pl', 'windows-1250')
def polish_char_map(seq: bytes) -> bytes:
    raw = encode('#$%+/;<=>@]^_`', encoding='ascii')
    transformed = encode('ęśłóćńÜżźąŁŚĘŻ', encoding='windows-1250')
    assert len(transformed) == len(set(transformed))
    tf = dict(zip(raw, transformed, strict=True))
    return bytes(tf.get(c, c) for c in seq)


@register(decrypts, 'ru', 'windows-1251')
def russian_char_map(seq: bytes) -> bytes:
    raw = encode(
        r'<=>@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghjkmnopqrstuvwxyz',
        encoding='ascii',
    )
    transformed = encode(
        'ьъэщАБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭыюязкЯабвгдеёжийлмонпрстуфхцчш',
        encoding='windows-1251',
    )
    assert len(transformed) == len(set(transformed))
    tf = dict(zip(raw, transformed, strict=True))
    return bytes(tf.get(c, c) for c in seq)


def identity_map(seq: bytes) -> bytes:
    return seq


def decrypt(
    msg: bytes,
    char_map: CharMapper,
    encoding: EncodeSettings = RAW_BYTE_ENCODING,
) -> str:
    return char_map(msg).decode(**encoding)
