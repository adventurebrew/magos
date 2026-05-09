from collections.abc import Callable
from string import printable
from typing import NewType, TypedDict, cast

CharMapper = NewType('CharMapper', bytes)
CharMapperFactory = Callable[[], CharMapper]


class EncodeSettings(TypedDict):
    encoding: str
    errors: str


RAW_BYTE_ENCODING = EncodeSettings(encoding='ascii', errors='surrogateescape')


_decrypts: dict[str, tuple[CharMapperFactory, EncodeSettings]] = {}
_tables: dict[str, tuple[CharMapper, EncodeSettings]] = {}
_revtables: dict[str, tuple[CharMapper, EncodeSettings]] = {}


def register_code(
    code: str,
    encoding: str,
    errors: str = 'strict',
) -> Callable[[CharMapperFactory], CharMapperFactory]:
    def wrapper(factory: CharMapperFactory) -> CharMapperFactory:
        _decrypts[code] = (factory, EncodeSettings(encoding=encoding, errors=errors))
        return factory

    return wrapper


def resolve_table(code: str) -> tuple[CharMapper, EncodeSettings]:
    resolved = _tables.get(code)
    if resolved is None:
        factory, encoding = _decrypts.get(code, (raw_char_map, RAW_BYTE_ENCODING))
        resolved = (factory(), encoding)
        _tables[code] = resolved
    return resolved


def resolve_reverse_table(code: str) -> tuple[CharMapper, EncodeSettings]:
    resolved = _revtables.get(code)
    if resolved is None:
        char_map, encoding = resolve_table(code)
        resolved = (reverse_map(char_map), encoding)
        _revtables[code] = resolved
    return resolved


def make_translation(raw: bytes, transformed: bytes) -> CharMapper:
    assert len(raw) == len(transformed)
    assert len(transformed) == len(set(transformed))
    return cast('CharMapper', bytes.maketrans(raw, transformed))


def reverse_map(mapper: CharMapper) -> CharMapper:
    printable_bytes = printable.encode('ascii')
    return make_translation(printable_bytes.translate(mapper), printable_bytes)


# @register_code('raw', 'ascii', errors='surrogateescape')
def raw_char_map() -> CharMapper:
    return cast('CharMapper', bytes(range(256)))


@register_code('he', 'windows-1255')
def hebrew_char_map() -> CharMapper:
    return make_translation(
        bytes(range(ord('@'), ord('Z') + 1)),
        bytes(c + 0xA0 for c in range(ord('@'), ord('Z') + 1)),
    )


@register_code('de', 'windows-1252')
def german_char_map() -> CharMapper:
    return make_translation(
        str.encode('#$+/;<=>', encoding='ascii'),
        str.encode('äößÄÖÜüé', encoding='windows-1252'),
    )


@register_code('es', 'windows-1252')
def spanish_char_map() -> CharMapper:
    return make_translation(
        str.encode('/;<=>@^_`', encoding='ascii'),
        str.encode('éàíóúñ¿¡ü', encoding='windows-1252'),
    )


@register_code('fr', 'windows-1252')
def french_char_map() -> CharMapper:
    return make_translation(
        str.encode('#$+/;<=>@^_`', encoding='ascii'),
        str.encode('ôâÇéàûèêîçïù', encoding='windows-1252'),
    )


@register_code('it', 'windows-1252')
def italian_char_map() -> CharMapper:
    return make_translation(
        str.encode('+/;<=`', encoding='ascii'),
        str.encode('ìéàòèù', encoding='windows-1252'),
    )


@register_code('pl', 'windows-1250')
def polish_char_map() -> CharMapper:
    return make_translation(
        str.encode('#$%+/;<=>@]^_`', encoding='ascii'),
        str.encode('ęśłóćńÜżźąŁŚĘŻ', encoding='windows-1250'),
    )


@register_code('ru', 'windows-1251')
def russian_char_map() -> CharMapper:
    return make_translation(
        str.encode(
            r'<=>@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghjkmnopqrstuvwxyz',
            encoding='ascii',
        ),
        str.encode(
            'ьъэщАБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭыюязкЯабвгдеёжийлмонпрстуфхцчш',
            encoding='windows-1251',
        ),
    )


def decrypt(
    msg: bytes,
    char_map: CharMapper,
    encoding: EncodeSettings = RAW_BYTE_ENCODING,
) -> str:
    return msg.translate(char_map).decode(**encoding)


def decrypt_by_code(
    msg: bytes,
    code: str,
) -> str:
    char_map, encoding = resolve_table(code)
    return decrypt(msg, char_map, encoding)


def encrypt(
    msg: str,
    char_map: CharMapper,
    encoding: EncodeSettings = RAW_BYTE_ENCODING,
) -> bytes:
    return msg.encode(**encoding).translate(char_map)


def encrypt_by_code(
    msg: str,
    code: str,
) -> bytes:
    char_map, encoding = resolve_reverse_table(code)
    return encrypt(msg, char_map, encoding)


def available_codes() -> list[str]:
    return list(_decrypts.keys())
