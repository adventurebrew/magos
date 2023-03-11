from dataclasses import dataclass
from typing import IO, TYPE_CHECKING

from magos.stream import read_uint32be, write_uint32be

if TYPE_CHECKING:
    from collections.abc import Sequence

KNOWN_GAMEPC_VERSION = 128


@dataclass
class GameBasefileInfo:
    total_item_count: int
    version: int
    item_count: int
    texts: 'Sequence[bytes]'
    tables: bytes


def read_gamepc(stream: IO[bytes]) -> GameBasefileInfo:
    total_item_count = read_uint32be(stream)
    version = read_uint32be(stream)
    assert version == KNOWN_GAMEPC_VERSION, version
    item_count = read_uint32be(stream)
    string_table_count = read_uint32be(stream)

    total_item_count += 2
    item_count += 2

    text_size = read_uint32be(stream)
    texts = stream.read(text_size).split(b'\0')
    last_text = texts.pop()
    assert last_text == b''
    assert len(texts) == string_table_count, (len(texts), string_table_count)

    tables = stream.read()
    return GameBasefileInfo(
        total_item_count,
        version,
        item_count,
        texts,
        tables,
    )


def write_gamepc(
    total_item_count: int,
    version: int,
    item_count: int,
    texts: 'Sequence[bytes]',
    tables_data: bytes,
) -> bytes:
    texts_content = b'\0'.join(texts) + b'\0'
    return (
        write_uint32be(total_item_count - 2)
        + write_uint32be(version)
        + write_uint32be(item_count - 2)
        + write_uint32be(len(texts))
        + write_uint32be(len(texts_content))
        + texts_content
        + tables_data
    )
