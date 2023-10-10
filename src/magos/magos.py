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
    BASE_MIN,
    Item,
    ItemType,
    Param,
    ParseError,
    Parser,
    PropertyType,
    load_tables,
    ops_mia,
    parse_props,
    parse_tables,
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
from magos.stream import create_directory
from magos.voice import extract_voices, rebuild_voices

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from magos.chiper import CharMapper, EncodeSettings
    from magos.gamepc import GameBasefileInfo
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
    base_min = BASE_MIN
    base_q: deque[int] = deque()
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
                        prop['name'].resolve(all_strings),
                        file=output_file,
                    )
                    description = prop['params'].pop(PropertyType.DESCRIPTION, None)
                    if description:
                        assert isinstance(description, Param)
                        print(
                            '\tDESCRIPTION',
                            description.value,
                            '//',
                            description.resolve(all_strings),
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
                    strict=True,
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
    soundmap: 'Mapping[int, set[int]] | None' = None,
) -> 'Iterator[tuple[Any, ...]]':
    for fname, lines in strings.items():
        for idx, line in lines.items():
            extra_info: tuple[Any, ...] = ()
            if soundmap:
                samples: 'Iterable[int] | None' = soundmap.get(idx, None)
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
    text_files: list[tuple[str, int]],
) -> 'Iterator[tuple[str, Sequence[Table]]]':
    script_data = scr_file.read()
    blank, *tables = script_data.split('== FILE')
    assert not blank, blank
    line_number = 1
    min_key = max_key = BASE_MIN
    for table in tables:
        tidx, *subs = table.split('SUBROUTINE')
        fname = tidx.split()[0]
        line_number += tidx.count('\n')
        tname = fname.replace('TABLES', 'TEXT')
        max_key = next((key for name, key in text_files if name == tname), max_key)
        parsed: list['Table'] = []
        for sub in subs:
            sidx, *lines = sub.split('== LINE ')
            try:
                parsed.extend(
                    parse_tables(
                        lines,
                        parser,
                        range(min_key, max_key),
                    ),
                )
            except ParseError as exc:
                exc.file = fname
                exc.sidx = sidx.strip()
                exc.line_number += line_number + sidx.count('\n')
                exc.show(scr_file.name)
                raise
            line_number += sub.count('\n')
        min_key = max_key
        yield fname, parsed


def dump_tables(
    stream: IO[bytes],
    scr_file: IO[str],
    gparser: Parser,
    all_strings: 'Mapping[int, str]',
    *,
    soundmap: dict[int, set[int]] | None = None,
) -> None:
    for tab in load_tables(stream, gparser, soundmap=soundmap):
        for line in tab.resolve(all_strings):
            print(line, file=scr_file)


def print_subs(
    fname: str,
    scr_file: IO[str],
    *,
    subs: 'Sequence[tuple[int, int]]' = ((0, 0),),
) -> 'Iterator[int]':
    print('== FILE', fname, subs, file=scr_file)
    for sub in subs:
        print('SUBROUTINE', sub, file=scr_file)
        yield from range(sub[0], sub[1] + 1)


def write_scripts(
    subtables: 'Iterable[tuple[Sequence[tuple[int, int]], str, bytes]]',
    scr_file: IO[str],
    gparser: Parser,
    all_strings: 'Mapping[int, str]',
    *,
    soundmap: dict[int, set[int]] | None = None,
) -> None:
    for subs, fname, content in subtables:
        with io.BytesIO(content) as stream:
            for _ in print_subs(fname, scr_file, subs=subs):
                dump_tables(
                    stream,
                    scr_file,
                    gparser,
                    all_strings,
                    soundmap=soundmap,
                )


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
    crypt: str | None
    output: Path
    extract: Path | None
    game: str | None
    script: str | None
    dump: Path
    items: Path
    voice: 'Sequence[str]'
    rebuild: bool
    unicode: bool
    voice_base: Path = Path('voices')


def menu(args: 'Sequence[str] | None' = None) -> CLIParams:
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
        help='File to output game strings to (default: strings.txt)',
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
        '--items',
        '-i',
        type=Path,
        default=Path('objects.txt'),
        required=False,
        help='File to output game items to (default: objects.txt)',
    )
    parser.add_argument(
        '--dump',
        '-d',
        type=Path,
        default=Path('scripts.txt'),
        required=False,
        help='File to output game scripts to (default: scripts.txt)',
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


@dataclass
class OutputConfig:
    map_char: 'CharMapper'
    encoding: 'EncodeSettings'
    output_encoding: 'EncodeSettings'


class GameInfo:
    basedir: Path
    basefile: str
    archive: 'MutableMapping[str, bytes]'
    text_files: 'Sequence[tuple[str, int]]'
    filenames: 'Sequence[str]'
    gbi: 'GameBasefileInfo'

    def __init__(self, args: CLIParams) -> None:
        filename = Path(args.filename)
        self.basedir = filename if args.many else filename.parent
        self.game = args.game or auto_detect_game_from_filename(filename)
        self.text_files = list(index_texts(self.game, self.basedir))

        self.filenames = list(get_packed_filenames(self.game, self.basedir))
        self.basefile = base_files[self.game]
        extra = bytearray()
        if args.many:
            self.archive = DirectoryBackedArchive(self.basedir, allowed=self.filenames)
        else:
            self.archive = {
                fname: content
                for _, fname, content in read_gme(self.filenames, filename, extra)
            }

        self.extra = bytes(extra)

        with (self.basedir / self.basefile).open('rb') as game_file:
            self.gbi = read_gamepc(game_file)
            assert game_file.read() == b''

    def parser(self, script: str) -> Parser:
        return Parser(
            optables[self.game][script],
            text_mask=0xFFFF0000 if self.game == 'simon1' else 0,
        )


def extract(
    game: GameInfo,
    args: CLIParams,
    oc: OutputConfig,
    voices: 'Iterable[Path]',
) -> None:
    if args.extract is not None and not args.many:
        extract_archive(game.archive, args.extract)

    strings = {}
    strings[game.basefile] = build_strings(oc.map_char, oc.encoding, game.gbi.texts)
    for fname, texts, base_min in extract_texts(game.archive, game.text_files):
        strings[fname] = build_strings(oc.map_char, oc.encoding, texts, start=base_min)
    write_tsv(
        make_strings(strings),
        args.output,
        encoding=oc.output_encoding,
    )

    if args.script:
        soundmap: dict[int, set[int]] | None = (
            defaultdict(set) if args.script == 'talkie' else None
        )
        gparser = game.parser(args.script)
        tables = list(index_table_files(game.basedir / 'TBLLIST'))
        all_strings = flatten_strings(strings)

        with io.BytesIO(game.gbi.tables) as stream:
            objects = read_objects(
                stream,
                game.gbi.item_count,
                soundmap=soundmap,
            )
            table_pos = stream.tell()

        write_objects(
            objects,
            args.items,
            all_strings,
            encoding=oc.output_encoding,
        )

        subtables = [
            (((0, 0),), game.basefile, memoryview(game.gbi.tables)[table_pos:]),
            *((subs, fname, game.archive[fname]) for fname, subs in tables),
        ]

        with args.dump.open('w', **oc.output_encoding) as scr_file:
            write_scripts(
                subtables,
                scr_file,
                gparser,
                all_strings,
                soundmap=soundmap,
            )

        if soundmap is not None:
            write_tsv(
                make_strings(strings, soundmap=soundmap),
                args.output,
                encoding=oc.output_encoding,
            )

    for voice in voices:
        extract_voices(voice, args.voice_base / Path(voice).name)


def rebuild(
    game: GameInfo,
    args: CLIParams,
    oc: OutputConfig,
    voices: 'Iterable[Path]',
) -> None:
    map_char = reverse_map(oc.map_char)
    if args.extract is not None and not args.many:
        patch_archive(game.archive, args.extract)

    with args.output.open('r', **oc.output_encoding) as string_file:
        tsv_file = split_lines(csv.reader(string_file, delimiter='\t'))
        reordered = sorted(tsv_file, key=operator.itemgetter(0, 1))
        bstrings = dict(read_strings(reordered, map_char, oc.encoding))
    gamepc_texts = list(bstrings.pop(game.basefile).values())

    text_files = list(update_text_index(game.text_files, bstrings))
    compose_stripped(text_files)

    for tfname, lines_in_group in bstrings.items():
        assert tfname in dict(text_files), tfname
        content = b'\0'.join(lines_in_group.values()) + b'\0'
        game.archive[tfname] = content

    tables_data = game.gbi.tables
    if args.script:
        gparser = game.parser(args.script)
        with args.items.open('r', **oc.output_encoding) as objects_file:
            objects = list(load_objects(objects_file))

        with args.dump.open('r', **oc.output_encoding) as scr_file:
            btables = dict(compile_tables(scr_file, gparser, text_files))

        base_tables = btables.pop(game.basefile)
        with io.BytesIO(game.gbi.tables) as tbl_file:
            _orig_objects = read_objects(tbl_file, game.gbi.item_count)
            _pref = game.gbi.tables[: tbl_file.tell()]
            _orig = list(load_tables(tbl_file, gparser))
            leftover = tbl_file.read()

        objects_pref = write_objects_bytes(objects)
        tables_data = objects_pref + rewrite_tables(base_tables) + leftover

        for fname, ftables in btables.items():
            game.archive[fname] = rewrite_tables(ftables)

    extra = game.extra
    if not args.many:
        write_gme(
            merge_packed([game.archive[afname] for afname in game.filenames]),
            args.filename.name,
            extra=extra,
        )

    base_content = write_gamepc(
        game.gbi.total_item_count,
        game.gbi.version,
        game.gbi.item_count,
        gamepc_texts,
        tables_data,
    )
    Path(game.basefile).write_bytes(base_content)

    voices = sorted(Path(vf.name) for vf in voices)
    for voice in voices:
        voice_dir = args.voice_base / voice
        if voice_dir.is_dir():
            rebuild_voices(voice, voice_dir)


def main(args: CLIParams) -> None:
    map_char, encoding = decrypts.get(
        args.crypt or 'raw',
        (identity_map, RAW_BYTE_ENCODING),
    )
    output_encoding = (
        cast('EncodeSettings', dict(encoding, encoding='utf-8'))
        if args.unicode
        else encoding
    )
    oc = OutputConfig(map_char, encoding, output_encoding)

    error_stream = sys.stderr

    filename = Path(args.filename)
    if not filename.exists():
        print(f"ERROR: file '{filename}' does not exists.", file=error_stream)
        sys.exit(1)

    try:
        game = GameInfo(args)
    except ValueError as exc:
        print(f'ERROR: {exc}', file=error_stream)
        sys.exit(1)

    print(f'Detected as {game.game}', file=error_stream)

    voices = sorted(
        set(chain.from_iterable(Path().glob(r) for r in args.voice)),
    )

    if not args.rebuild:
        extract(game, args, oc, voices)
    else:
        rebuild(game, args, oc, voices)

    for opcode, occurences in ops_mia.items():
        print(
            f'WARNING: Unknown opcode 0x{opcode:02X} appears {occurences} times',
            file=error_stream,
        )


if __name__ == '__main__':
    main(menu())
