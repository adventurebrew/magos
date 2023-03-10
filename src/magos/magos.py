import argparse
import csv
import io
import itertools
import operator
import sys
from collections import defaultdict, deque
from collections.abc import MutableMapping
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Deque,
    Optional,
    cast,
)

from magos.agos_opcode import (
    feeble_ops,
    simon2_ops,
    simon2_ops_talkie,
    simon_ops,
    simon_ops_talkie,
    waxworks_ops,
)
from magos.chiper import (
    RAW_BYTE_ENCODING,
    decrypt,
    decrypts,
    identity_map,
    reverse_map,
)
from magos.gamepc import read_gamepc, write_gamepc
from magos.gamepc_script import (
    Item,
    ItemType,
    Param,
    Parser,
    PropertyType,
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
from magos.stream import create_directory, write_uint32le
from magos.voice import extract_voices, rebuild_voices

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from magos.chiper import CharMapper, EncodeSettings
    from magos.gamepc_script import Table
    from magos.stream import FilePath

supported_games = (
    'waxworks',
    'feeble',
    'simon1',
    'simon2',
)

base_files = {
    'waxworks': 'GAMEPC',
    'feeble': 'GAME22',
    'simon1': 'GAMEPC',
    'simon2': 'GSPTR30',
}

optables = {
    'waxworks': {
        'floppy': waxworks_ops,
    },
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


class GameNotDetectedError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            'could not detect game automatically, '
            'please provide specific game using --game option',
        )


def auto_detect_game_from_filename(filename: 'FilePath') -> str:
    filename = Path(filename)
    if 'simon2' in filename.name.lower():
        return 'simon2'
    if 'simon' in filename.name.lower():
        return 'simon1'
    raise GameNotDetectedError


def flatten_strings(strings: 'Mapping[str, Mapping[int, str]]') -> dict[int, str]:
    return dict(chain.from_iterable(lines.items() for _, lines in strings.items()))


def split_lines(strings: 'Iterable[Sequence[str]]') -> 'Iterator[tuple[str, int, str]]':
    for line in strings:
        fname, idx, msg, *rest = line
        yield fname, int(idx), msg


def extract_archive(archive: 'Mapping[str, bytes]', target_dir: 'FilePath') -> None:
    target_dir = Path(target_dir)
    create_directory(target_dir)
    for fname, content in archive.items():
        (target_dir / fname).write_bytes(content)


def patch_archive(
    archive: 'MutableMapping[str, bytes]',
    target_dir: 'FilePath',
) -> None:
    target_dir = Path(target_dir)
    for fname, _ in archive.items():
        if (target_dir / fname).exists():
            archive[fname] = (target_dir / fname).read_bytes()


def build_strings(
    map_char: 'CharMapper',
    encoding: 'EncodeSettings',
    texts: 'Iterable[bytes]',
    start: int = 0,
) -> dict[int, str]:
    return dict(
        enumerate((decrypt(msg, map_char, encoding) for msg in texts), start=start),
    )


def extract_texts(
    archive: 'Mapping[str, bytes]',
    text_files: 'Iterable[tuple[str, int]]',
) -> 'Iterator[tuple[str, Sequence[bytes], int]]':
    base_min = 0x8000
    base_q: Deque[int] = deque()
    for fname, base_max in text_files:
        base_q.append(base_max)
        texts = archive[fname].split(b'\0')
        last_text = texts.pop()
        assert last_text == b''
        yield fname, texts, base_min
        if texts:
            base_min = base_q.popleft()


def write_objects(
    objects: 'Sequence[Item]',
    output: 'FilePath',
    all_strings: 'Mapping[int, str]',
    encoding: 'EncodeSettings',
) -> None:
    output = Path(output)
    with output.open('w', **encoding) as output_file:
        for obj in objects:
            print(
                '== DEFINE {} {} {} {} {} {} {} {} {} =='.format(
                    obj['adjective'],
                    obj['noun'],
                    obj['state'],
                    obj['next_item'],
                    obj['child'],
                    obj['parent'],
                    obj['unk'],
                    obj['item_class'],
                    obj['properties_init'],
                ),
                file=output_file,
            )
            for prop in obj['properties']:
                print(f'==> {prop["ptype"].name}', file=output_file)
                if prop['ptype'] == ItemType.OBJECT:
                    print(
                        '\tNAME',
                        prop['name'].value,
                        '//',
                        f'{{{prop["name"].resolve(all_strings)}}}',
                        file=output_file,
                    )
                    description = prop['params'].pop(PropertyType.DESCRIPTION, None)
                    if description:
                        assert isinstance(description, Param)
                        print(
                            '\tDESCRIPTION',
                            description.value,
                            '//',
                            f'{{{description.resolve(all_strings)}}}',
                            file=output_file,
                        )
                    for pkey, pval in prop['params'].items():
                        print(f'\t{pkey.name}', pval, file=output_file)
                elif prop['ptype'] == ItemType.ROOM:
                    print('\tTABLE', prop['table'], file=output_file)
                    for idx, ex in enumerate(prop['exits']):
                        print(
                            f'\tEXIT{1+idx}',
                            f"{ex['exit_to']} {ex['status'].name}"
                            if ex is not None
                            else '-',
                            file=output_file,
                        )
                elif prop['ptype'] == ItemType.INHERIT:
                    print('\tITEM', prop['item'], file=output_file)
                elif prop['ptype'] == ItemType.USERFLAG:
                    print('\t1', prop['flag1'], file=output_file)
                    print('\t2', prop['flag2'], file=output_file)
                    print('\t3', prop['flag3'], file=output_file)
                    print('\t4', prop['flag4'], file=output_file)
                else:
                    raise ValueError(prop)


def load_objects(objects_file: IO[str]) -> 'Iterator[Item]':
    objects_data = objects_file.read()
    blank, *defs = objects_data.split('== DEFINE')
    assert not blank, blank
    for do in defs:
        rlidx, *props = do.split('==> ')
        lidx = [int(x) for x in rlidx.split('==')[0].split() if x]
        yield cast(
            Item,
            dict(
                zip(
                    (
                        'adjective',
                        'noun',
                        'state',
                        'next_item',
                        'child',
                        'parent',
                        'unk',
                        'item_class',
                        'properties_init',
                        'properties',
                    ),
                    (*lidx, list(parse_props(props))),
                ),
            ),
        )


def write_tsv(
    items: 'Iterable[tuple[Any, ...]]',
    output: 'FilePath',
    encoding: 'EncodeSettings',
) -> None:
    output = Path(output)
    with output.open('w', **encoding, newline='') as output_file:
        writer = csv.writer(output_file, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
        writer.writerows(items)


def make_strings(
    strings: 'Mapping[str, Mapping[int, str]]',
    soundmap: 'Optional[Mapping[int, set[int]]]' = None,
) -> 'Iterator[tuple[Any, ...]]':
    for fname, lines in strings.items():
        for idx, line in lines.items():
            extra_info: tuple[Any, ...] = ()
            if soundmap:
                samples: 'Optional[Iterable[int]]' = soundmap.get(idx, None)
                lsample = -1
                if samples is not None:
                    samples = sorted(samples)
                    lsample = samples.pop()
                    for s in samples:
                        yield (fname, idx, line, s, 'DUP')
                extra_info = (lsample,)
            yield (fname, idx, line, *extra_info)


def read_strings(
    string_file: 'Iterable[tuple[str, int, str]]',
    map_char: 'CharMapper',
    encoding: 'EncodeSettings',
) -> 'Iterator[tuple[str, dict[int, bytes]]]':
    grouped = itertools.groupby(string_file, key=operator.itemgetter(0))
    for tfname, group in grouped:
        assert isinstance(tfname, str)
        basename = Path(tfname).name

        lines_in_group: dict[int, bytes] = {}
        for _, idx, line in group:
            lines_in_group[idx] = map_char(line.encode(**encoding))
        yield basename, lines_in_group


class DirectoryBackedArchive(MutableMapping[str, bytes]):
    def __init__(self, directory: 'FilePath', allowed: 'Iterable[str]' = ()) -> None:
        self.directory = Path(directory)
        self._allowed = frozenset(allowed)
        self._cache: dict[str, bytes] = {}

    def __setitem__(self, key: str, content: bytes) -> None:
        if key not in self._allowed:
            raise KeyError(key)
        Path(key).write_bytes(content)
        self._cache[key] = content

    def __getitem__(self, key: str) -> bytes:
        if key in self._cache:
            return self._cache[key]
        if key not in self._allowed:
            raise KeyError(key)
        return (self.directory / key).read_bytes()

    def __iter__(self) -> 'Iterator[str]':
        return iter(self._allowed)

    def __len__(self) -> int:
        return len(self._allowed)

    def __delitem__(self, key: str) -> None:
        self._cache.pop(key)


def index_texts(game: str, basedir: Path) -> 'Iterator[tuple[str, int]]':
    if game == 'feeble':
        yield from ()
        return
    yield from index_text_files(basedir / 'STRIPPED.TXT')


def rewrite_tables(tables: 'Iterable[Table]') -> bytes:
    if not tables:
        return b''
    return b'\0\0' + b'\0\0'.join(bytes(tab) for tab in tables) + b'\0\1'


def compile_tables(
    scr_file: IO[str],
    parser: Parser,
) -> 'Iterator[tuple[str, Sequence[Table]]]':
    script_data = scr_file.read()
    blank, *tables = script_data.split('== FILE')
    assert not blank, blank
    for table in tables:
        tidx, *subs = table.split('SUBROUTINE')
        fname = tidx.split()[0]
        parsed: list['Table'] = []
        for sub in subs:
            sidx, *lines = sub.split('== LINE ')
            parsed.extend(parse_tables(lines, parser))
        yield fname, parsed


def dump_tables(
    fname: str,
    stream: IO[bytes],
    scr_file: IO[str],
    subs: 'Optional[Sequence[tuple[int, int]]]' = None,
) -> None:
    if subs is None:
        subs = ((0, 0),)
    print('== FILE', fname, subs, file=scr_file)
    for sub in subs:
        print('SUBROUTINE', sub, file=scr_file)
        for _ in range(sub[0], sub[1] + 1):
            for tab in load_tables(stream, gparser, soundmap=soundmap):
                for line in tab.resolve(all_strings):
                    print(line, file=scr_file)


def update_text_index(
    text_files: 'Iterable[tuple[str, int]]',
    strings: 'Mapping[str, Mapping[int, bytes]]',
) -> 'Iterator[tuple[str, int]]':
    for (tfname, _orig_max_key), keys in itertools.zip_longest(
        text_files,
        strings.values(),
    ):
        if keys:
            max_key = max(keys)
        max_key += 1
        yield tfname, max_key


@dataclass
class CLIParams:
    filename: Path
    many: bool
    crypt: 'Optional[str]'
    output: Path
    extract: 'Optional[Path]'
    game: 'Optional[str]'
    script: 'Optional[str]'
    dump: Path
    voice: 'Sequence[str]'
    rebuild: bool
    unicode: bool


def menu(args: 'Optional[Sequence[str]]' = None) -> CLIParams:

    parser = argparse.ArgumentParser(
        description='Process resources for Simon the Sorcerer.',
    )
    parser.add_argument(
        'filename',
        type=Path,
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
        help='Optional text decryption method',
    )
    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        default=Path('strings.txt'),
        required=False,
        help='File to output game strings to',
    )
    parser.add_argument(
        '--extract',
        '-e',
        type=Path,
        default=None,
        required=False,
        help='Optionally specify directory to extract file from .GME',
    )
    parser.add_argument(
        '--game',
        '-g',
        choices=supported_games,
        default=None,
        required=False,
        help=(
            'Specific game to extract '
            '(will attempt to infer from file name if not provided)'
        ),
    )
    parser.add_argument(
        '--script',
        '-s',
        choices=optables['simon1'].keys(),
        default=None,
        required=False,
        help='Script optable to dump script with (skipped if not provided)',
    )
    parser.add_argument(
        '--dump',
        '-d',
        type=Path,
        default=Path('scripts.txt'),
        required=False,
        help='File to output game scripts to',
    )
    parser.add_argument(
        '--voice',
        '-t',
        nargs='+',
        type=str,
        default=(),
        required=False,
        help='Sound file(s) with voices to extract',
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

    return CLIParams(**vars(parser.parse_args(args)))


if __name__ == '__main__':
    args = menu()

    map_char, encoding = decrypts.get(
        args.crypt or 'raw',
        (identity_map, RAW_BYTE_ENCODING),
    )
    output_encoding = (
        cast('EncodeSettings', dict(encoding, encoding='utf-8'))
        if args.unicode
        else encoding
    )
    filename = Path(args.filename)
    basedir = filename if args.many else filename.parent

    if not filename.exists():
        print(f"ERROR: file '{filename}' does not exists.")
        sys.exit(1)

    try:
        game = args.game or auto_detect_game_from_filename(filename)
    except ValueError as exc:
        print(f'ERROR: {exc}')
        sys.exit(1)

    print(f'Detected as {game}')
    text_files = list(index_texts(game, basedir))

    filenames = list(get_packed_filenames(game, basedir))
    basefile = base_files[game]
    archive: 'MutableMapping[str, bytes]'
    if args.many:
        archive = DirectoryBackedArchive(basedir, allowed=filenames)
    else:
        archive = {
            fname: content for _, fname, content in read_gme(filenames, filename)
        }

    voice_base = Path('voices')
    voices = sorted(
        set(chain.from_iterable(Path('.').glob(r) for r in args.voice)),
    )

    with (basedir / basefile).open('rb') as game_file:
        total_item_count, version, item_count, gamepc_texts, tables_data = read_gamepc(
            game_file,
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
            soundmap: Optional[dict[int, set[int]]] = (
                defaultdict(set) if args.script == 'talkie' else None
            )
            gparser = Parser(
                optables[game][args.script],
                text_mask=0xFFFF0000 if game == 'simon1' else 0,
            )
            tables = list(index_table_files(basedir / 'TBLLIST'))
            all_strings = flatten_strings(strings)

            with args.dump.open('w', **output_encoding) as scr_file:
                with io.BytesIO(tables_data) as stream:
                    objects = read_objects(
                        stream,
                        item_count,
                        soundmap=soundmap,
                    )
                    dump_tables(basefile, stream, scr_file)

                for fname, subs in tables:
                    with io.BytesIO(archive[fname]) as tbl_file:
                        dump_tables(fname, tbl_file, scr_file, subs)

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
            extract_voices(voice, voice_base / Path(voice).name)

    else:
        map_char = reverse_map(map_char)
        if args.extract is not None and not args.many:
            patch_archive(archive, args.extract)

        with args.output.open('r', **output_encoding) as string_file:
            tsv_file = split_lines(csv.reader(string_file, delimiter='\t'))
            reordered = sorted(tsv_file, key=operator.itemgetter(0, 1))
            bstrings = dict(read_strings(reordered, map_char, encoding))
        gamepc_texts = list(bstrings.pop(basefile).values())

        text_files = list(update_text_index(text_files, bstrings))
        compose_stripped(text_files)

        for tfname, lines_in_group in bstrings.items():
            assert tfname in dict(text_files), tfname
            content = b'\0'.join(lines_in_group.values()) + b'\0'
            archive[tfname] = content

        if args.script:
            gparser = Parser(
                optables[game][args.script],
                text_mask=0xFFFF0000 if game == 'simon1' else 0,
            )

            with Path('objects.txt').open('r', **output_encoding) as objects_file:
                gobjects = list(load_objects(objects_file))

            with args.dump.open('r', **output_encoding) as scr_file:
                btables = dict(compile_tables(scr_file, gparser))

            base_tables = btables.pop(basefile)
            with io.BytesIO(tables_data) as tbl_file:
                _orig_objects = [read_object(tbl_file) for i in range(2, item_count)]
                pref = tables_data[: tbl_file.tell()]
                orig = list(load_tables(tbl_file, gparser))
                leftover = tbl_file.read()

            objects_pref = write_objects_bytes(gobjects)
            tables_data = objects_pref + rewrite_tables(base_tables) + leftover

            for fname, ftables in btables.items():
                archive[fname] = rewrite_tables(ftables)

        extra = write_uint32le(481) if game == 'simon2' else b''
        if not args.many:
            write_gme(
                merge_packed([archive[afname] for afname in filenames]),
                filename.name,
                extra=extra,
            )

        base_content = write_gamepc(
            total_item_count,
            version,
            item_count,
            gamepc_texts,
            tables_data,
        )
        Path(basefile).write_bytes(base_content)

        voices = sorted(Path(vf.name) for vf in voices)
        for voice in voices:
            voice_dir = voice_base / voice
            if voice_dir.is_dir():
                rebuild_voices(voice, voice_dir)
