from collections import abc, defaultdict, deque
import csv
import glob
import io
from itertools import chain
import itertools
import operator
import os
import pathlib
from typing import Iterable, Iterator

from magos.chiper import (
    RAW_BYTE_ENCODING,
    CharMapper,
    EncodeSettings,
    decrypt,
    decrypts,
    identity_map,
    reverse_map,
)
from magos.gamepc import read_gamepc, write_gamepc
from magos.gamepc_script import (
    Parser,
    load_tables,
    parse_props,
    parse_tables,
    read_object,
    read_objects,
    write_objects_bytes,
)
from magos.gmepack import (
    compose_stripped,
    get_packed_filenames,
    index_table_files,
    index_text_files,
    merge_packed,
    read_gme,
    write_gme,
)
from magos.voice import extract_voices, rebuild_voices
from magos.stream import create_directory, write_uint16be, write_uint32le
from magos.agos_opcode import (
    simon_ops,
    simon2_ops,
    simon_ops_talkie,
    simon2_ops_talkie,
    feeble_ops,
)


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
        yield fname, int(idx), msg


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


def write_objects(objects, output, all_strings, encoding: EncodeSettings):
    with open(output, 'w', **encoding) as output_file:
        for obj in objects[2:]:
            print(
                '== DEFINE {} {} {} {} {} {} {} {} {} =='.format(
                    obj['adjective'],
                    obj['noun'],
                    obj['state'],
                    obj['next'],
                    obj['child'],
                    obj['parent'],
                    obj['unk'],
                    obj['class'],
                    obj['properties_init'],
                ),
                file=output_file,
            )
            for prop in obj['properties']:
                print(f'==> {prop["type"]}', file=output_file)
                if prop['type'] == 'OBJECT':
                    print(
                        '\tNAME',
                        prop['name'].value,
                        '//',
                        f'{{{prop["name"].resolve(all_strings)}}}',
                        file=output_file,
                    )
                    description = prop['params'].pop('description', None)
                    if description:
                        print(
                            '\tDESCRIPTION',
                            description.value,
                            '//',
                            f'{{{description.resolve(all_strings)}}}',
                            file=output_file,
                        )
                    for pkey, pval in prop['params'].items():
                        print(f'\t{pkey.upper()}', pval, file=output_file)
                elif prop['type'] == 'ROOM':
                    print('\tTABLE', prop['table'], file=output_file)
                    print('\tEXIT_STATE', prop['exit_states'], file=output_file)
                    print('\tEXITS', '|'.join(prop['exits']) or '-', file=output_file)
                else:
                    raise ValueError(prop)


def load_objects(objects_file):
    objects_data = objects_file.read()
    blank, *defs = objects_data.split('== DEFINE')
    assert not blank, blank
    for do in defs:
        lidx, *props = do.split('==> ')
        lidx = [int(x) for x in lidx.split('==')[0].split() if x]
        yield dict(
            zip(
                (
                    'adjective',
                    'noun',
                    'state',
                    'next',
                    'child',
                    'parent',
                    'unk',
                    'class',
                    'properties_init',
                    'properties',
                ),
                (*lidx, list(parse_props(props))),
            )
        )


def write_tsv(items, output, encoding: EncodeSettings):
    with open(output, 'w', **encoding, newline='') as output_file:
        writer = csv.writer(output_file, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
        writer.writerows(items)


def make_strings(strings, soundmap=None):
    for fname, lines in strings.items():
        for idx, line in lines.items():
            extra_info = ()
            if soundmap:
                samples = soundmap.get(idx, -1)
                lsample = samples
                if samples != -1:
                    samples = sorted(samples)
                    lsample = samples.pop()
                    for s in samples:
                        yield (fname, idx, line, s, 'DUP')
                extra_info = (lsample,)
            yield (fname, idx, line, *extra_info)


def read_strings(string_file, map_char: CharMapper, encoding: EncodeSettings):
    grouped = itertools.groupby(string_file, key=operator.itemgetter(0))
    for tfname, group in grouped:
        basename = os.path.basename(tfname)

        lines_in_group = {}
        for _, idx, line in group:
            lines_in_group[idx] = map_char(line.encode(**encoding))
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


def rewrite_tables(tables):
    if not tables:
        return b''
    return b'\0\0' + b'\0\0'.join(bytes(tab) for tab in tables) + b'\0\1'


def compile_tables(scr_file, parser):
    script_data = scr_file.read()
    blank, *tables = script_data.split('== FILE')
    assert not blank, blank
    for table in tables:
        tidx, *subs = table.split('SUBROUTINE')
        fname = tidx.split()[0]
        parsed = []
        for sub in subs:
            sidx, *lines = sub.split('== LINE ')
            parsed.extend(parse_tables(lines, parser))
        yield fname, parsed


def update_text_index(text_files, strings):
    for (tfname, orig_max_key), keys in itertools.zip_longest(text_files, strings.values()):
        if keys:
            max_key = max(keys)
        max_key += 1
        # assert orig_max_key == max_key, (orig_max_key, max_key)
        yield tfname, max_key


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
    parser.add_argument(
        '--unicode',
        '-u',
        action='store_true',
        required=False,
        help='Convert output to unicode',
    )

    args = parser.parse_args()

    map_char, encoding = decrypts.get(
        args.crypt,
        (identity_map, RAW_BYTE_ENCODING),
    )
    output_encoding = dict(encoding, encoding='utf-8') if args.unicode else encoding
    filename = args.filename
    basedir = pathlib.Path(filename if args.many else os.path.dirname(filename))

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
            encoding=output_encoding,
        )

        if args.script:
            soundmap = defaultdict(set) if args.script == 'talkie' else None
            parser = Parser(
                optables[game][args.script],
                text_mask=0xFFFF0000 if game == 'simon1' else 0,
            )
            tables = list(index_table_files(basedir / 'TBLLIST'))
            all_strings = flatten_strings(strings)

            with open(args.dump, 'w', **output_encoding) as scr_file:
                with io.BytesIO(tables_data) as stream:
                    print('== FILE', basefile, file=scr_file)

                    # objects[1] is the player
                    objects = read_objects(
                        stream,
                        item_count,
                        soundmap=soundmap,
                    )

                    print('SUBROUTINE', None, file=scr_file)
                    for t in load_tables(stream, parser, soundmap=soundmap):
                        for l in t.resolve(all_strings):
                            print(l, file=scr_file)

                for fname, subs in tables:
                    print('== FILE', fname, subs, file=scr_file)
                    with io.BytesIO(archive[fname]) as tbl_file:
                        for sub in subs:
                            print('SUBROUTINE', sub, file=scr_file)
                            for i in range(sub[0], sub[1] + 1):
                                for t in load_tables(
                                    tbl_file, parser, soundmap=soundmap
                                ):
                                    for l in t.resolve(all_strings):
                                        print(l, file=scr_file)

            write_objects(
                objects,
                'objects.txt',
                all_strings,
                encoding=output_encoding,
            )

            if soundmap is not None:
                write_tsv(
                    make_strings(strings, soundmap=soundmap),
                    args.output,
                    encoding=output_encoding,
                )

        for voice in voices:
            extract_voices(voice, os.path.join('voices', os.path.basename(voice)))

    else:
        map_char = reverse_map(map_char)
        if args.extract is not None and not args.many:
            patch_archive(archive, args.extract)

        with open(args.output, 'r', **output_encoding) as string_file:
            tsv_file = split_lines(csv.reader(string_file, delimiter='\t'))
            reordered = sorted(tsv_file, key=operator.itemgetter(0, 1))
            strings = dict(read_strings(reordered, map_char, encoding))
        gamepc_texts = list(strings.pop(basefile).values())

        text_files = list(update_text_index(text_files, strings))
        compose_stripped(text_files)

        for tfname, lines_in_group in strings.items():
            assert tfname in dict(text_files).keys(), tfname
            content = b'\0'.join(lines_in_group.values()) + b'\0'
            # assert archive[tfname] == content, (tfname, archive[tfname].split(b'\0'), content.split(b'\0'))
            archive[tfname] = content

        if args.script:
            parser = Parser(
                optables[game][args.script],
                text_mask=0xFFFF0000 if game == 'simon1' else 0,
            )

            with open('objects.txt', 'r', **output_encoding) as objects_file:
                objects = list(load_objects(objects_file))

            objects_pref = write_objects_bytes(objects)

            with open(args.dump, 'r', **output_encoding) as scr_file:
                tables = dict(compile_tables(scr_file, parser))

            base_tables = tables.pop(basefile)
            with io.BytesIO(tables_data) as tbl_file:
                list(read_object(tbl_file) for i in range(2, item_count))
                pref = tables_data[: tbl_file.tell()]
                orig = list(load_tables(tbl_file, parser))
                leftover = tbl_file.read()
            tables_data = objects_pref + rewrite_tables(base_tables) + leftover

            for fname, ftables in tables.items():
                archive[fname] = rewrite_tables(ftables)

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
