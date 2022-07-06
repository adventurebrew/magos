from collections import deque
import io
from itertools import chain
import itertools
import operator
import os
import pathlib
import re

from magos.chiper import decrypt, hebrew_char_map, identity_map, reverse_map
from magos.gamepc import read_gamepc, write_gamepc
from magos.gamepc_script import load_tables, read_object
from magos.gmepack import get_packed_filenames, index_table_files, index_text_files, merge_packed, read_gme, write_gme
from magos.voice import read_voc_soundbank
from magos.stream import create_directory, write_uint32le
from magos.agos_opcode import simon_ops, simon2_ops, simon_ops_talkie, simon2_ops_talkie


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


def split_lines(strings):
    for line in strings:
        fname, idx, msg, *rest = line.rstrip('\n').split('\t')
        yield fname, idx, msg


def extract_archive(archive, target_dir):
    target_dir = pathlib.Path(target_dir)
    create_directory(target_dir)
    for fname, content in archive.items():
        (target_dir / fname).write_bytes(content)


def patch_archive(archive, target_dir):
    target_dir = pathlib.Path(target_dir)
    for fname, _ in archive.items():
        if (target_dir / fname).exists():
            archive[fname] = (target_dir / fname).read_bytes()


def build_strings(map_char, encoding, texts, start=0):
    return dict(enumerate((decrypt(msg, map_char, encoding) for msg in texts), start=start))


def extract_texts(archive, text_files):
    base_min = 0x8000
    base_q = deque()
    for fname, base_max in text_files:
        base_q.append(base_max)
        texts = archive[fname].split(b'\0')
        last_text = texts.pop()
        assert last_text == b''
        yield fname, texts, base_min
        if texts:
            base_min = base_q.popleft()


def write_tsv(items, output, encoding):
    with open(output, 'w', encoding=encoding) as output_file:
        for item in items:
            print(*item, sep='\t', file=output_file)


def make_strings(strings, soundmap=None):
    for fname, lines in strings.items():
        for idx, line in lines.items(): 
            extra_info = () if soundmap is None else (soundmap.get(idx, -1),)
            yield (fname, idx, line, *extra_info)


def extract_voices(voice_file, target_dir):
    target_dir = pathlib.Path(target_dir)
    base, ext = os.path.splitext(os.path.basename(voice_file))
    with open(voice_file, 'rb') as soundbank:
        os.makedirs(target_dir, exist_ok=True)
        for idx, vocdata in read_voc_soundbank(soundbank):
            (target_dir / f'{idx:04d}{ext}').write_bytes(vocdata)


def rebuild_voices(voice_file, target_dir):
    target_dir = pathlib.Path(target_dir)
    base, ext = os.path.splitext(os.path.basename(voice_file))

    def extract_number(sfile):
        s = re.findall(f"(\d+).{ext}", sfile)
        return (int(s[0]) if s else -1, sfile)

    maxfile = max(os.listdir(target_dir), key=extract_number)
    maxnum = int(maxfile[:-len(ext)])
    print(maxnum)
    offset = 4 * (maxnum + 1)
    ind = bytearray(b'\0\0\0\0')
    cont = bytearray()
    for idx in range(maxnum):
        sfile = (target_dir / f'{1 + idx:04d}{ext}')
        content = b''
        if sfile.exists():
            content = sfile.read_bytes()
        # yield offset, content
        ind += write_uint32le(offset)
        cont += content
        offset += len(content)

    pathlib.Path((base + ext)).write_bytes(ind + cont)


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
    parser.add_argument('--rebuild', '-r',  action='store_true', required=False, help='Rebuild modified game resources')

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

    with open(basedir / basefile, 'rb') as game_file:
        total_item_count, version, item_count, gamepc_texts, tables_data = read_gamepc(game_file)
        assert game_file.read() == b''

    if not args.rebuild:
        if args.extract is not None:
            extract_archive(archive, args.extract)

        strings = {}
        strings[basefile] = build_strings(map_char, encoding, gamepc_texts)
        for fname, texts, base_min in extract_texts(archive, text_files):
            strings[fname] = build_strings(map_char, encoding, texts, start=base_min)
        write_tsv(
            make_strings(strings),
            args.output,
            encoding=encoding,
        )

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

            write_tsv(
                ((item,) for item in objects),
                'objects.txt',
                encoding=encoding,
            )

            if soundmap is not None:
                write_tsv(
                    make_strings(strings, soundmap=soundmap),
                    args.output,
                    encoding=encoding,
                )

        if args.voice:
            extract_voices(args.voice, 'voices')

    else:
        map_char = reverse_map(map_char)
        if args.extract is not None:
            patch_archive(archive, args.extract)

        with open(args.output, 'r') as string_file:
            grouped = itertools.groupby(split_lines(string_file), key=operator.itemgetter(0))
            for tfname, group in grouped:
                basename = os.path.basename(tfname)
                lines_in_group = [map_char(line.encode(encoding)) for _, _, line in group]
                content =  b'\0'.join(lines_in_group) + b'\0'
                if tfname in archive:
                    # assert archive[tfname] == content, (tfname, archive[tfname].split(b'\0'), content.split(b'\0'))
                    archive[tfname] = content
                else:
                    assert tfname == basefile, (tfname, basefile)
                    base_content = write_gamepc(total_item_count, version, item_count, lines_in_group, tables_data)
                    # assert base_content == pathlib.Path(basedir / basefile).read_bytes()

        extra = write_uint32le(481) if game == 'simon2' else b''
        write_gme(
            merge_packed([archive[afname] for afname in filenames]),
            os.path.basename(filename),
            extra=extra,
        )
        pathlib.Path(basefile).write_bytes(base_content)

        if args.voice:
            rebuild_voices(args.voice, 'voices')
