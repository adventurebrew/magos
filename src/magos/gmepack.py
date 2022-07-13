import os
from itertools import chain
from os import PathLike
import pathlib
import struct
from typing import Union

from magos.stream import read_uint16be, readcstr, write_uint32le


def read_subroutines(stream):
    while True:
        min_sub = read_uint16be(stream)
        if min_sub == 0:
            break
        max_sub = read_uint16be(stream)
        yield min_sub, max_sub


def index_table_files(tbllist_path: str):
    with open(tbllist_path, 'rb') as stream:
        while True:
            fname = readcstr(stream)
            if not fname:
                break
            subroutines = tuple(read_subroutines(stream))
            yield fname.decode(), subroutines


def index_text_files(stripped_path: str):
    with open(stripped_path, 'rb') as stream:
        while True:
            name = stream.read(7)
            if not name:
                break
            base_max = read_uint16be(stream)
            yield name.rstrip(b'\0').decode(), base_max


def read_gme(filenames, input_file):
    with open(input_file, 'rb') as gme_file:
        num_reads = len(filenames)
        offsets = struct.unpack(f'<{num_reads}I', gme_file.read(4 * num_reads))

        if gme_file.tell() < offsets[0]:
            print('UNKNOWN EXTRA', struct.unpack(f'<I', gme_file.read(4))[0])

        sizes = (
            nextoff - offset
            for offset, nextoff in zip(offsets, offsets[1:] + offsets[-1:])
        )
        assert gme_file.tell() == offsets[0], (gme_file.tell(), offsets[0])

        for offset, filename, size in zip(offsets, filenames, sizes):
            assert gme_file.tell() == offset, (gme_file.tell(), offset)
            yield offset, filename, gme_file.read(size)

        rest = gme_file.read()
        assert rest == b'', rest


def merge_packed(archive):
    num = len(archive)
    offset = num * 4
    for content in archive:
        yield offset, content
        offset += len(content)


def write_gme(streams, filename, extra=b''):
    offsets, contents = zip(*streams)
    lxtra = len(extra)
    with open(filename, 'wb') as gme_file:
        gme_file.write(b''.join(write_uint32le(off + lxtra) for off in offsets))
        gme_file.write(extra)
        gme_file.write(b''.join(contents))


def get_packed_filenames(game: str, basedir: Union[str, PathLike] = '.'):
    basedir = pathlib.Path(basedir)
    if game == 'simon1':
        # Simon the Sorcerer
        yield from chain.from_iterable(
            (f'{vga:03d}1.VGA', f'{vga:03d}2.VGA') for vga in range(164)
        )
        yield from ['UNKNOWN.BIN']  # unknown file
        yield from ['MOD{:d}.MUS'.format(idx) for idx in range(36)]
        yield 'EMPTYFILE'
        yield from (fname for fname, _ in index_text_files(basedir / 'STRIPPED.TXT'))
        yield from (fname for fname, _ in index_table_files(basedir / 'TBLLIST'))
        yield 'EMPTYFILE'
        return

    if game == 'simon2':
        # Simon the Sorcerer 2
        yield from chain.from_iterable(
            (f'{vga:03d}1.VGA', f'{vga:03d}2.VGA') for vga in range(141)
        )
        yield from ['HI{:d}.XMI'.format(idx) for idx in range(1, 94)]
        yield 'EMPTYFILE'
        yield from (fname for fname, _ in index_text_files(basedir / 'STRIPPED.TXT'))
        yield from (fname for fname, _ in index_table_files(basedir / 'TBLLIST'))
        yield 'EMPTYFILE'
        yield from ['SFX{:d}.VOC'.format(idx) for idx in range(1, 20)]
        yield from ['LO{:d}.XMI'.format(idx) for idx in range(1, 94)]
        yield 'EMPTYFILE'
        return

    if game == 'feeble':
        yield from os.listdir(basedir)
        return

    raise NotImplementedError(game)
