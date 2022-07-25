from collections import abc, deque
import csv
import glob
import io
from itertools import chain
import itertools
import operator
import os
import pathlib
from typing import Iterable, Iterator

from magos.chiper import decrypt, hebrew_char_map, identity_map, reverse_map
from magos.gamepc import read_gamepc, write_gamepc
from magos.gamepc_script import load_tables, read_object
from magos.gmepack import (
    get_packed_filenames,
    index_table_files,
    index_text_files,
    merge_packed,
    read_gme,
    write_gme,
)
from magos.voice import extract_voices, rebuild_voices
from magos.stream import create_directory, write_uint32le
from magos.agos_opcode import (
    simon_ops,
    simon2_ops,
    simon_ops_talkie,
    simon2_ops_talkie,
    feeble_ops,
)


decrypts = {
    'he': hebrew_char_map,
}

supported_games = (
    'feeble',
    'simon1',
    'simon2',
)

base_files = {
    'feeble': 'GAME22',
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
    },
    'feeble': {
        'talkie': feeble_ops,
    },
}


def auto_detect_game_from_filename(filename):
    if 'simon2' in os.path.basename(filename).lower():
        return 'simon2'
    elif 'simon' in os.path.basename(filename).lower():
        return 'simon1'
    raise ValueError(
        'could not detect game automatically, please provide specific game using --game option'
    )


def flatten_strings(strings):
    return dict(chain.from_iterable(lines.items() for _, lines in strings.items()))


def split_lines(strings):
    for line in strings:
        fname, idx, msg, *rest = line
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
    return dict(
        enumerate((decrypt(msg, map_char, encoding) for msg in texts), start=start)
    )


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
    with open(output, 'w', encoding=encoding, newline='') as output_file:
        writer = csv.writer(output_file, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
        writer.writerows(items)


def make_strings(strings, soundmap=None):
    for fname, lines in strings.items():
        for idx, line in lines.items():
            extra_info = () if soundmap is None else (soundmap.get(idx, -1),)
            yield (fname, idx, line, *extra_info)


def read_strings(string_file, map_char, encoding):
    grouped = itertools.groupby(string_file, key=operator.itemgetter(0))
    for tfname, group in grouped:
        basename = os.path.basename(tfname)
        lines_in_group = {
            int(idx): map_char(line.encode(encoding)) for _, idx, line in group
        }
        yield basename, lines_in_group


class DirectoryBackedArchive(abc.MutableMapping):
    def __init__(self, directory, allowed: Iterable[str] = ()) -> None:
        self.directory = pathlib.Path(directory)
        self._allowed = frozenset(allowed)
        self._cache = {}

    def __setitem__(self, key: str, content: bytes) -> None:
        if key not in self._allowed:
            raise KeyError(key)
        pathlib.Path(key).write_bytes(content)
        self._cache[key] = content

    def __getitem__(self, key: str) -> bytes:
        if key in self._cache:
            return self._cache[key]
        if key not in self._allowed:
            raise KeyError(key)
        return (self.directory / key).read_bytes()

    def __iter__(self) -> Iterator[str]:
        return iter(self._allowed)

    def __len__(self) -> int:
        return len(self._allowed)

    def __delitem__(self, key: str) -> None:
        self._cache.pop(key)


def index_texts(game, basedir):
    if game == 'feeble':
        yield from ()
        return
    yield from index_text_files(basedir / 'STRIPPED.TXT')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Process resources for Simon the Sorcerer.'
    )
    parser.add_argument(
        'filename',
        help='Path to the game data file to extract texts from (e.g. SIMON.GME)',
    )
    parser.add_argument(
        '--many',
        '-m',
        action='store_true',
        required=False,
        help='Mark the directory with data files as already extracted',
    )
    parser.add_argument(
        '--crypt',
        '-c',
        choices=decrypts.keys(),
        default=None,
        required=False,
        help=f'Optional text decryption method',
    )
    parser.add_argument(
        '--output',
        '-o',
        default='strings.txt',
        required=False,
        help=f'File to output game strings to',
    )
    parser.add_argument(
        '--extract',
        '-e',
        type=str,
        default=None,
        required=False,
        help=f'Optionally specify directory to extract file from .GME',
    )
    parser.add_argument(
        '--game',
        '-g',
        choices=supported_games,
        default=None,
        required=False,
        help=f'Specific game to extract (will attempt to infer from file name if not provided)',
    )
    parser.add_argument(
        '--script',
        '-s',
        choices=optables['simon1'].keys(),
        default=None,
        required=False,
        help=f'Script optable to dump script with (skipped if not provided)',
    )
    parser.add_argument(
        '--dump',
        '-d',
        default='scripts.txt',
        required=False,
        help=f'File to output game scripts to',
    )
    parser.add_argument(
        '--voice',
        '-t',
        nargs='+',
        type=str,
        default=(),
        required=False,
        help=f'Sound file(s) with voices to extract',
    )
    parser.add_argument(
        '--rebuild',
        '-r',
        action='store_true',
        required=False,
        help='Rebuild modified game resources',
    )

    args = parser.parse_args()

    map_char = decrypts.get(args.crypt, identity_map)
    filename = args.filename
    basedir = pathlib.Path(filename if args.many else os.path.dirname(filename))
    encoding = 'windows-1255'

    if not os.path.exists(filename):
        print('ERROR: file \'{}\' does not exists.'.format(filename))
        exit(1)

    try:
        game = args.game or auto_detect_game_from_filename(filename)
    except ValueError as exc:
        print(f'ERROR: {exc}')
        exit(1)

    print(f'Detected as {game}')
    text_files = list(index_texts(game, basedir))

    filenames = list(get_packed_filenames(game, basedir))
    basefile = base_files[game]
    if args.many:
        archive = DirectoryBackedArchive(basedir, allowed=filenames)
    else:
        archive = {
            fname: content for _, fname, content in read_gme(filenames, filename)
        }

    voices = sorted(set(chain.from_iterable(glob.iglob(r) for r in args.voice)))

    with open(basedir / basefile, 'rb') as game_file:
        total_item_count, version, item_count, gamepc_texts, tables_data = read_gamepc(
            game_file
        )
        assert game_file.read() == b''

    if not args.rebuild:
        if args.extract is not None and not args.many:
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
                    objects = [null, player] + [
                        read_object(stream, all_strings, soundmap=soundmap)
                        for i in range(2, item_count)
                    ]

                    for t in load_tables(
                        stream, all_strings, optable, soundmap=soundmap
                    ):
                        print(t, file=scr_file)

                for fname, subs in tables:
                    print(fname, subs, file=scr_file)
                    with io.BytesIO(archive[fname]) as tbl_file:
                        for sub in subs:
                            print('SUBROUTINE', sub, file=scr_file)
                            for i in range(sub[0], sub[1] + 1):
                                for t in load_tables(
                                    tbl_file, all_strings, optable, soundmap=soundmap
                                ):
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

        for voice in voices:
            extract_voices(voice, os.path.join('voices', os.path.basename(voice)))

    else:
        map_char = reverse_map(map_char)
        if args.extract is not None and not args.many:
            patch_archive(archive, args.extract)

        with open(args.output, 'r') as string_file:
            tsv_file = split_lines(csv.reader(string_file, delimiter='\t'))
            strings = dict(read_strings(tsv_file, map_char, encoding))
        gamepc_texts = list(strings.pop(basefile).values())
        for tfname, lines_in_group in strings.items():
            assert tfname in dict(text_files).keys(), tfname
            content = b'\0'.join(lines_in_group.values()) + b'\0'
            # assert archive[tfname] == content, (tfname, archive[tfname].split(b'\0'), content.split(b'\0'))
            archive[tfname] = content

        extra = write_uint32le(481) if game == 'simon2' else b''
        if not args.many:
            write_gme(
                merge_packed([archive[afname] for afname in filenames]),
                os.path.basename(filename),
                extra=extra,
            )
        base_content = write_gamepc(
            total_item_count, version, item_count, gamepc_texts, tables_data
        )
        # assert base_content == pathlib.Path(basedir / basefile).read_bytes()
        pathlib.Path(basefile).write_bytes(base_content)

        voices = sorted(os.path.basename(vf) for vf in voices)
        for voice in voices:
            voice_dir = os.path.join('voices', voice)
            if os.path.isdir(voice_dir):
                rebuild_voices(voice, voice_dir)
