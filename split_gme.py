import os
import struct
import sys

from chiper import decrypt, hebrew_char_map, identity_map
from gmepack import get_packed_filenames, index_text_files
from stream import create_directory


def read_gme(filenames, input_file):
    with open(input_file, 'rb') as gme_file:
        num_reads = len(filenames)
        offsets = struct.unpack(f'<{num_reads}I', gme_file.read(4 * num_reads))

        if gme_file.tell() < offsets[0]:
            print('UNKNOWN EXTRA', struct.unpack(f'<I', gme_file.read(4))[0])

        sizes = (nextoff - offset for offset, nextoff in zip(offsets, offsets[1:] + offsets[-1:]))
        assert gme_file.tell() == offsets[0], (gme_file.tell(), offsets[0])

        for offset, filename, size in zip(offsets, filenames, sizes):
            assert gme_file.tell() == offset, (gme_file.tell(), offset)
            yield offset, filename, gme_file.read(size)

        rest = gme_file.read()
        assert rest == b'', rest


def splitbins(input_file, filenames):
    create_directory('temps')
    
    for offset, filename, content in read_gme(filenames, input_file):
        print(offset, filename, len(content))
        with open('temps/' + filename, 'wb') as tempFile:
            tempFile.write(content)



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

    text_files = [fname for fname, _ in index_text_files('STRIPPED.TXT')]
    filenames = list(get_packed_filenames('simon1'))

    offsets = splitbins(filename, filenames)

    make_texts(text_files, map_char, encoding='windows-1255')
