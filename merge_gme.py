import struct
import operator
import itertools
import pathlib
import sys

from chiper import hebrew_char_map, identity_map
from gmepack import get_packed_filenames
from stream import write_uint32le

TEMPS_DIR = pathlib.Path('temps')

def split_lines(lines):
    for line in lines:
        fname, idx, line = line.rstrip('\n').split('\t')
        yield fname, idx, line


def collect_texts(map_char, encoding='windows-1255'):
    with open('texts/texts.txt', 'r', encoding=encoding) as text_file:
        grouped = itertools.groupby(split_lines(text_file), key=operator.itemgetter(0))
        for fname, group in grouped:
            lines_in_group = [map_char(line.encode(encoding)) for _, _, line in group]
            fpath = TEMPS_DIR / fname
            fpath.write_bytes(b'\0'.join(lines_in_group) + b'\0')


def merge_files(files):
    num = len(files)
    size = num * 4
    for fname in files:
        fpath = TEMPS_DIR / fname
        content = fpath.read_bytes()
        yield size, content
        size += len(content)


def write_output(filename, streams):
    offsets, contents = zip(*streams)
    with open(filename, 'wb') as gmeFile:
        gmeFile.write(b''.join(write_uint32le(off) for off in offsets))
        gmeFile.write(b''.join(contents))


if __name__ == '__main__':
    map_char = identity_map
    filename = 'SIMON-NEW.GME'
    try:
        filename = sys.argv[1]
        if filename in ('--decrypt', '-d'):
            if sys.argv[2] == 'he':
                map_char = hebrew_char_map
            else:
                raise IndexError
            filename = sys.argv[3]
    except IndexError as e:
        print('Usage:\n' + 'python merge-gme.py [--decrypt he] SIMON-NEW.GME')
        exit(1)

    if filename in ('', '.', '..', '/'):
        print('Error: can\'t create file without name')
        exit(1)

    filenames = list(get_packed_filenames('simon1'))

    collect_texts(map_char)

    write_output(filename, merge_files(filenames))
