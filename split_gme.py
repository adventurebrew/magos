import os
import struct

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


decrypts = {
    'he': hebrew_char_map,
}


supported_games = (
    'simon1',
    'simon2',
)


def auto_detect_game_from_filename(filename):
    if 'simon2' in os.path.basename(filename).lower():
        return 'simon2'
    elif 'simon' in os.path.basename(filename).lower():
        return 'simon1'
    raise ValueError('could not detect game automatically, please provide specific game using --game option')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('filename', help='Path to the game data file to unpack (e.g. SIMON.GME)')
    parser.add_argument('--decrypt', '-d', choices=decrypts.keys(), default=None, required=False, help=f'Optional text decryption method')
    parser.add_argument('--game', '-g', choices=supported_games, default=None, required=False, help=f'Specific game to unpack (will attempt to infere from file name if not provided)')

    args = parser.parse_args()

    map_char = decrypts.get(args.decrypt, identity_map)
    filename = args.filename

    if not os.path.exists(filename):
        print('ERROR: file \'{}\' does not exists.'.format(filename))
        exit(1)

    try:
        game = args.game or auto_detect_game_from_filename(args.filename)
    except ValueError as exc:
        print(f'ERROR: {exc}')
        exit(1)

    print(f'Attempt to unpack as {game}')
    text_files = [fname for fname, _ in index_text_files('STRIPPED.TXT')]
    filenames = list(get_packed_filenames(game))

    splitbins(filename, filenames)

    make_texts(text_files, map_char, encoding='windows-1255')
