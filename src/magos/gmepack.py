import os
import struct
from collections import defaultdict
from itertools import chain
from pathlib import Path
from typing import IO, TYPE_CHECKING

from magos.detection import GameID
from magos.stream import (
    read_uint16be,
    readcstr,
    write_uint16be,
    write_uint32le,
)
from magos.zone import get_zone_filenames

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, MutableSequence, Sequence

    from magos.stream import FilePath


def read_subroutines(stream: IO[bytes]) -> 'Iterator[tuple[int, int]]':
    while True:
        min_sub = read_uint16be(stream)
        if min_sub == 0:
            break
        max_sub = read_uint16be(stream)
        yield min_sub, max_sub


def index_table_files_elvira(
    tbllist_path: 'FilePath',
) -> 'Iterator[tuple[str, Sequence[tuple[int, int]]]]':
    tbllist_path = Path(tbllist_path)
    if not tbllist_path.exists():
        return
    sentinel = 242
    with tbllist_path.open('rb') as stream:
        msubs = defaultdict(list)
        _header = stream.read(32)

        while True:
            min_sub = read_uint16be(stream)
            max_sub = read_uint16be(stream)
            file_num = ord(stream.read(1))
            unk = ord(stream.read(1))
            if min_sub == 0:
                break
            assert unk == 1, unk
            msubs[file_num].append((min_sub, max_sub))
        assert stream.read() == b'', stream.read()
        assert unk == sentinel, unk
        for file_num, subs in msubs.items():
            yield f'TABLES{file_num:02d}', tuple(subs)


def create_table_index_elvira(
    subs: 'dict[str, Sequence[tuple[int, int]]]',
) -> bytes:
    index = bytearray()
    for fname, subroutines in subs.items():
        fidx = int(fname.removeprefix('TABLES'))
        for min_sub, max_sub in subroutines:
            index += write_uint16be(min_sub) + write_uint16be(max_sub)
            index += bytes([fidx, 1])
    index += b'\0\0\0\0\x03\xf2'
    return index


def index_table_files(
    tbllist_path: 'FilePath',
) -> 'Iterator[tuple[str, Sequence[tuple[int, int]]]]':
    tbllist_path = Path(tbllist_path)
    if not tbllist_path.exists():
        return
    with tbllist_path.open('rb') as stream:
        while True:
            fname = readcstr(stream)
            if not fname:
                break
            subroutines = tuple(read_subroutines(stream))
            yield fname.decode(), subroutines
        assert stream.read() == b'', stream.read()


def create_table_index(
    subs: 'dict[str, Sequence[tuple[int, int]]]',
) -> bytes:
    index = bytearray()
    for fname, subroutines in subs.items():
        index += fname.encode() + b'\0'
        for min_sub, max_sub in subroutines:
            index += write_uint16be(min_sub) + write_uint16be(max_sub)
        index += b'\0\0'
    index += b'\0'
    return bytes(index)


def index_text_files(stripped_path: 'FilePath') -> 'Iterator[tuple[str, int]]':
    stripped_path = Path(stripped_path)
    if not stripped_path.exists():
        return
    with stripped_path.open('rb') as stream:
        while True:
            name = stream.read(7)
            if not name:
                break
            base_max = read_uint16be(stream)
            yield name.rstrip(b'\0').decode('ascii'), base_max


def compose_tables_index(
    tables_index: 'Mapping[str, dict[str, Sequence[tuple[int, int]]]]',
    game: 'GameID',
    archive: 'Mapping[str, bytes]',
) -> None:
    (index_tables, create_index) = (
        (index_table_files_elvira, create_table_index_elvira)
        if game <= GameID.elvira2
        else (index_table_files, create_table_index)
    )

    for fname, sub_index in tables_index.items():
        header = b''
        if game <= GameID.elvira2:
            # TODO: Understand header values to avoid copying from original file
            header = archive[fname][:32]
        tbllist = Path(fname)
        tid = create_index(sub_index)
        tbllist.write_bytes(header + tid)
        assert dict(index_tables(tbllist)) == sub_index


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


def get_packed_filenames(
    archive: str | None,
    basedir: 'FilePath' = '.',
) -> 'Iterator[str]':
    basedir = Path(basedir)
    if archive == 'SIMON.GME':
        # Simon the Sorcerer
        yield from chain.from_iterable(get_zone_filenames(zone) for zone in range(164))
        yield from ['UNKNOWN.BIN']  # unknown file
        yield from [f'MOD{idx:d}.MUS' for idx in range(36)]
        yield 'EMPTYFILE'
        yield from (fname for fname, _ in index_text_files(basedir / 'STRIPPED.TXT'))
        yield from (fname for fname, _ in index_table_files(basedir / 'TBLLIST'))
        yield 'EMPTYFILE'
        return

    if archive == 'SIMON2.GME':
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

    assert archive is None, archive
    yield from os.listdir(basedir)
