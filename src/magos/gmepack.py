import os
import struct
from itertools import chain
from pathlib import Path
from typing import IO, TYPE_CHECKING

from magos.stream import (
    read_uint16be,
    readcstr,
    write_uint16be,
    write_uint32le,
)
from magos.zone import get_zone_filenames

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, MutableSequence, Sequence

    from magos.stream import FilePath


def read_subroutines(stream: IO[bytes]) -> 'Iterator[tuple[int, int]]':
    while True:
        min_sub = read_uint16be(stream)
        if min_sub == 0:
            break
        max_sub = read_uint16be(stream)
        yield min_sub, max_sub


def index_table_files(
    tbllist_path: 'FilePath',
) -> 'Iterator[tuple[str, Sequence[tuple[int, int]]]]':
    tbllist_path = Path(tbllist_path)
    with tbllist_path.open('rb') as stream:
        while True:
            fname = readcstr(stream)
            if not fname:
                break
            subroutines = tuple(read_subroutines(stream))
            yield fname.decode(), subroutines


def index_text_files(stripped_path: 'FilePath') -> 'Iterator[tuple[str, int]]':
    stripped_path = Path(stripped_path)
    with stripped_path.open('rb') as stream:
        while True:
            name = stream.read(7)
            if not name:
                break
            base_max = read_uint16be(stream)
            yield name.rstrip(b'\0').decode('ascii'), base_max


def compose_stripped(text_files: 'Iterable[tuple[str, int]]') -> None:
    stripped = bytearray()
    for tfname, max_key in text_files:
        stripped += tfname.encode('ascii') + b'\0' + write_uint16be(max_key)
    if stripped:
        Path('STRIPPED.TXT').write_bytes(stripped)


def read_gme(
    filenames: 'Sequence[str]',
    input_file: 'FilePath',
    extra: 'MutableSequence[int]',
) -> 'Iterator[tuple[int, str, bytes]]':
    input_file = Path(input_file)
    with input_file.open('rb') as gme_file:
        num_reads = len(filenames)
        offsets = struct.unpack(f'<{num_reads}I', gme_file.read(4 * num_reads))

        if gme_file.tell() < offsets[0]:
            extra += gme_file.read(offsets[0] - gme_file.tell())

        sizes = (
            nextoff - offset
            for offset, nextoff in zip(offsets, offsets[1:] + offsets[-1:], strict=True)
        )
        assert gme_file.tell() == offsets[0], (gme_file.tell(), offsets[0])

        for offset, filename, size in zip(offsets, filenames, sizes, strict=True):
            assert gme_file.tell() == offset, (gme_file.tell(), offset)
            yield offset, filename, gme_file.read(size)

        rest = gme_file.read()
        assert rest == b'', rest


def merge_packed(archive: 'Sequence[bytes]') -> 'Iterator[tuple[int, bytes]]':
    num = len(archive)
    offset = num * 4
    for content in archive:
        yield offset, content
        offset += len(content)


def write_gme(
    streams: 'Iterable[tuple[int, bytes]]',
    filename: 'FilePath',
    extra: bytes = b'',
) -> None:
    filename = Path(filename)
    offsets, contents = zip(*streams, strict=True)
    lxtra = len(extra)
    with filename.open('wb') as gme_file:
        gme_file.write(b''.join(write_uint32le(off + lxtra) for off in offsets))
        gme_file.write(extra)
        gme_file.write(b''.join(contents))


def get_packed_filenames(game: str, basedir: 'FilePath' = '.') -> 'Iterator[str]':
    basedir = Path(basedir)
    if game == 'simon1':
        # Simon the Sorcerer
        yield from chain.from_iterable(get_zone_filenames(zone) for zone in range(164))
        yield from ['UNKNOWN.BIN']  # unknown file
        yield from [f'MOD{idx:d}.MUS' for idx in range(36)]
        yield 'EMPTYFILE'
        yield from (fname for fname, _ in index_text_files(basedir / 'STRIPPED.TXT'))
        yield from (fname for fname, _ in index_table_files(basedir / 'TBLLIST'))
        yield 'EMPTYFILE'
        return

    if game == 'simon2':
        # Simon the Sorcerer 2
        yield from chain.from_iterable(get_zone_filenames(zone) for zone in range(141))
        yield from [f'HI{idx:d}.XMI' for idx in range(1, 94)]
        yield 'EMPTYFILE'
        yield from (fname for fname, _ in index_text_files(basedir / 'STRIPPED.TXT'))
        yield from (fname for fname, _ in index_table_files(basedir / 'TBLLIST'))
        yield 'EMPTYFILE'
        yield from [f'SFX{idx:d}.VOC' for idx in range(1, 20)]
        yield from [f'LO{idx:d}.XMI' for idx in range(1, 94)]
        yield 'EMPTYFILE'
        return

    if game == 'feeble':
        yield from os.listdir(basedir)
        return

    if game == 'waxworks':
        yield from os.listdir(basedir)
        return

    raise NotImplementedError(game)
