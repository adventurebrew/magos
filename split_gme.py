import os
import struct
import sys

from chiper import decrypt, hebrew_char_map, identity_map
from gmepack import get_packed_filenames, index_text_files
from stream import create_directory


def splitbins(input_file, filenames):
    create_directory('temps')
    with open(input_file, 'rb') as gmeFile:
        offsets = []
        offsets.append(struct.unpack('<I', gmeFile.read(4))[0])
        while gmeFile.tell() < offsets[0]:
            offsets.append(struct.unpack('<I', gmeFile.read(4))[0])

        for idx, offset in enumerate(offsets[:-1]):
            filename = filenames[idx] if len(filenames) > idx else 'tempfile{:04}.bin'.format(idx)
            with open('temps/' + filename, 'wb') as tempFile:
                tempFile.write(gmeFile.read(offsets[idx + 1] - offset))

        rest = gmeFile.read()
        if rest:
            with open('temps/ZZZ{:d}'.format(len(offsets)), 'wb') as tempFile:
                tempFile.write(rest)
    return offsets

def make_texts(textFiles, map_char, encoding):
    create_directory('texts')

    with open('texts/texts.txt', 'w', encoding=encoding) as strFile:
        for fname in textFiles:
            with open('temps/' + fname, 'rb') as tempFile:
                texts = tempFile.read().split(b'\0')
            last_text = texts.pop()
            assert last_text == b''
            strings = [decrypt(text, map_char, encoding) for text in texts]
            for idx, strr in enumerate(strings, start=0x8000):
                assert '\t' not in strr
                assert '\n' not in strr
                print(fname, idx, strr, file=strFile, sep='\t')


if __name__ == '__main__':
    map_char = identity_map
    filename = 'SIMON.GME'
    try:
        filename = sys.argv[1]
        if filename in ('--decrypt', '-d'):
            if sys.argv[2] == 'he':
                map_char = hebrew_char_map
            else:
                raise IndexError
            filename = sys.argv[3]
    except IndexError as e:
        print('Usage:\n' + 'python split-gme.py [--decrypt he] SIMON.GME')
        exit(1)

    if not os.path.exists(filename):
        print('Error: file \'{}\' does not exists.'.format(filename))
        exit(1)

    text_files = list(index_text_files('STRIPPED.TXT'))
    filenames = list(get_packed_filenames('simon1'))

    offsets = splitbins(filename, filenames)

    # print information to file to help tracking
    with open('offsets.txt', 'w') as offFile:
        last = 0
        for idx, off in enumerate(offsets):
            offFile.write('{} - {}: {} - {} = {} | {} \n'.format(idx, hex(idx), off, hex(off), last == off, filenames[idx] if idx < len(filenames) else 'TEMPFILE{:03d}'.format(idx)))
            last = off

    make_texts(text_files, map_char, encoding='windows-1255')
