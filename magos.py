from collections import deque
import io
from itertools import chain
import os
import pathlib

from chiper import decrypt, hebrew_char_map, identity_map
from gamepc import read_gamepc
from gamepc_script import load_tables, read_object
from gmepack import get_packed_filenames, index_table_files, index_text_files, read_gme
from voice import read_voc_soundbank
from stream import create_directory
from agos_opcode import simon_ops, simon2_ops, simon_ops_talkie, simon2_ops_talkie


decrypts = {
    'he': hebrew_char_map,
}

supported_games = (
    'simon1',
    'simon2',
)

base_files = {
    'simon1': 'GAMEPC',
    'simon2': 'GSPTR30',
}

optables = {
    'simon1': {
        'floppy': simon_ops,
        'talkie': simon_ops_talkie,
    },
    'simon2': {
        'floppy': simon2_ops,
        'talkie': simon2_ops_talkie,
    }
}

def auto_detect_game_from_filename(filename):
    if 'simon2' in os.path.basename(filename).lower():
        return 'simon2'
    elif 'simon' in os.path.basename(filename).lower():
        return 'simon1'
    raise ValueError('could not detect game automatically, please provide specific game using --game option')


def flatten_strings(strings):
    return dict(chain.from_iterable(lines.items() for _, lines in strings.items()))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Process resources for Simon the Sorcerer.')
    parser.add_argument('filename', help='Path to the game data file to extract texts from (e.g. SIMON.GME)')
    parser.add_argument('--crypt', '-c', choices=decrypts.keys(), default=None, required=False, help=f'Optional text decryption method')
    parser.add_argument('--output', '-o', default='strings.txt', required=False, help=f'File to output game strings to')
    parser.add_argument('--extract', '-e', type=str, default=None, required=False, help=f'Optionally specify directory to extract file from .GME')
    parser.add_argument('--game', '-g', choices=supported_games, default=None, required=False, help=f'Specific game to extract (will attempt to infer from file name if not provided)')
    parser.add_argument('--script', '-s', choices=optables['simon1'].keys(), default=None, required=False, help=f'Script optable to dump script with (skipped if not provided)')
    parser.add_argument('--dump', '-d', default='scripts.txt', required=False, help=f'File to output game scripts to')
    parser.add_argument('--voice', '-t', type=str, default=None, required=False, help=f'Sound file with voices to extract')

    args = parser.parse_args()

    map_char = decrypts.get(args.crypt, identity_map)
    filename = args.filename
    basedir = pathlib.Path(os.path.dirname(filename))
    encoding = 'windows-1255'

    if not os.path.exists(filename):
        print('ERROR: file \'{}\' does not exists.'.format(filename))
        exit(1)

    try:
        game = args.game or auto_detect_game_from_filename(args.filename)
    except ValueError as exc:
        print(f'ERROR: {exc}')
        exit(1)

    print(f'Detected as {game}')
    text_files = list(index_text_files(basedir / 'STRIPPED.TXT'))

    filenames = list(get_packed_filenames(game, basedir))
    basefile = base_files[game]
    archive = {filename: content for _, filename, content in read_gme(filenames, filename)}

    if args.extract is not None:
        target_dir = pathlib.Path(args.extract)
        create_directory(target_dir)
        for fname, content in archive.items():
            with open(target_dir / fname, 'wb') as out_file:
                out_file.write(content)

    strings = {}

    with open(basedir / basefile, 'rb') as game_file:
        total_item_count, version, item_count, gamepc_texts, tables_data = read_gamepc(game_file)
        assert game_file.read() == b''

    strings[basefile] = dict(enumerate(decrypt(msg, map_char, encoding) for msg in gamepc_texts))

    base_min = 0x8000
    base_q = deque()
    for fname, base_max in text_files:
        base_q.append(base_max)
        texts = archive[fname].split(b'\0')
        last_text = texts.pop()
        assert last_text == b''
        strings[fname] = dict(enumerate((decrypt(msg, map_char, encoding) for msg in texts), start=base_min))
        if strings[fname]:
            base_min = base_q.popleft()

    with open(args.output, 'w', encoding=encoding) as str_output: 
        for fname, lines in strings.items():
            for idx, line in lines.items():
                print(fname, idx, line, sep='\t', file=str_output)

    if args.script:
        soundmap = {} if args.script == 'talkie' else None
        optable = optables[game][args.script]
        tables = list(index_table_files(basedir / 'TBLLIST'))
        all_strings = flatten_strings(strings)

        with open(args.dump, 'w', encoding=encoding) as scr_file:
            with io.BytesIO(tables_data) as stream:
                # objects[1] is the player
                null = {'children': []}
                player = {'children': []}
                objects = [null, player] + [read_object(stream, all_strings, soundmap=soundmap) for i in range(2, item_count)]

                for t in load_tables(stream, all_strings, optable, soundmap=soundmap):
                    print(t, file=scr_file)

            for fname, subs in tables:
                print(fname, subs, file=scr_file)
                with io.BytesIO(archive[fname]) as tbl_file:
                    for sub in subs:
                        print('SUBROUTINE', sub, file=scr_file)
                        for i in range(sub[0], sub[1] + 1):
                            for t in load_tables(tbl_file, all_strings, optable, soundmap=soundmap):
                                print(t, file=scr_file)

        with open('objects.txt', 'w', encoding=encoding) as obj_file:
            for item in objects:
                print(item, file=obj_file)

        if soundmap is not None:
            with open(args.output, 'w', encoding=encoding) as str_output: 
                for fname, lines in strings.items():
                    for idx, line in lines.items():
                        soundid = soundmap.get(idx, -1)
                        print(fname, idx, line, soundid, sep='\t', file=str_output)

    if args.voice:
        target_dir = pathlib.Path('voices')
        base, ext = os.path.splitext(os.path.basename(args.voice))
        with open(args.voice, 'rb') as soundbank:
            os.makedirs(target_dir, exist_ok=True)
            for idx, vocdata in read_voc_soundbank(soundbank):
                (target_dir / f'{idx:04d}{ext}').write_bytes(vocdata)
