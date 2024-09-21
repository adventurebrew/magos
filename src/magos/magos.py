import argparse
import csv
import io
import itertools
import operator
import sys
from collections import defaultdict, deque
from collections.abc import MutableMapping
from dataclasses import dataclass
from functools import partial
from itertools import chain
from pathlib import Path
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    cast,
)

from magos.chiper import (
    RAW_BYTE_ENCODING,
    decrypt,
    decrypts,
    identity_map,
    reverse_map,
)
from magos.detection import (
    DetectionEntry,
    GameID,
    auto_detect_game_from_filenames,
    known_variants,
    optables,
)
from magos.gamepc import read_gamepc, write_gamepc
from magos.gamepc_script import (
    BASE_MIN,
    WORD_MASK,
    ElviraEoomProperty,
    ElviraObjectProperty,
    ElviraUserFlagProperty,
    GenExitProperty,
    Item,
    ItemType,
    ObjectProperty,
    Param,
    ParseError,
    Parser,
    PropertyType,
    RoomProperty,
    SuperRoomProperty,
    load_tables,
    ops_mia,
    parse_props,
    parse_tables,
    read_objects,
    write_objects_bytes,
)
from magos.gmepack import (
    compose_stripped,
    compose_tables_index,
    get_packed_filenames,
    index_table_files,
    index_table_files_elvira,
    index_text_files,
    merge_packed,
    read_gme,
    write_gme,
)
from magos.stream import create_directory
from magos.voice import extract_voices, rebuild_voices

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    from magos.chiper import CharMapper, EncodeSettings
    from magos.gamepc import GameBasefileInfo
    from magos.gamepc_script import Property, Table
    from magos.gmepack import SubRanges
    from magos.stream import FilePath


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


def resolve_strings(
    all_strings: 'Mapping[int, str]',
    param: 'Param',
) -> str:
    return param.resolve(all_strings)


def write_room_property_text(
    prop: 'Property',
    output: IO[str],
    resolve: 'Callable[[Param], str]',
) -> None:
    if prop.get('game') == GameID.elvira1:
        prop = cast(ElviraEoomProperty, prop)
        print('\tSHORT', prop['short'], '//', resolve(prop['short']), file=output)
        print('\tLONG', prop['long'], '//', resolve(prop['long']), file=output)
        print('\tFLAGS', prop['flags'], file=output)
    else:
        prop = cast(RoomProperty, prop)
        print('\tTABLE', prop['table'], file=output)
        for idx, ex in enumerate(prop['exits']):
            print(
                f'\tEXIT{1+idx}',
                f"{ex['exit_to']} {ex['status'].name}" if ex is not None else '-',
                file=output,
            )


def write_object_property_text(
    prop: 'Property',
    output: IO[str],
    resolve: 'Callable[[Param], str]',
) -> None:
    if prop.get('game') == GameID.elvira1:
        prop = cast(ElviraObjectProperty, prop)
        print('\tTEXT1', prop['text1'].value, '//', resolve(prop['text1']), file=output)
        print('\tTEXT2', prop['text2'].value, '//', resolve(prop['text2']), file=output)
        print('\tTEXT3', prop['text3'].value, '//', resolve(prop['text3']), file=output)
        print('\tTEXT4', prop['text4'].value, '//', resolve(prop['text4']), file=output)
        print('\tSIZE', prop['size'], file=output)
        print('\tWEIGHT', prop['weight'], file=output)
        print('\tFLAGS', prop['flags'], file=output)
    else:
        prop = cast(ObjectProperty, prop)
        if prop['name'] is not None:
            print(
                '\tNAME',
                prop['name'].value,
                '//',
                resolve(prop['name']),
                file=output,
            )
        description = prop['params'].pop(PropertyType.DESCRIPTION, None)
        if description:
            assert isinstance(description, Param)
            print(
                '\tDESCRIPTION',
                description.value,
                '//',
                resolve(description),
                file=output,
            )
        for pkey, pval in prop['params'].items():
            print(f'\t{pkey.name}', pval, file=output)


def write_super_room_genexit_property_text(
    prop: 'Property',
    output: IO[str],
    resolve: 'Callable[[Param], str]',
) -> None:
    if prop.get('game') == GameID.elvira1:
        prop = cast(GenExitProperty, prop)
        print('\tDEST1', prop['dest1'], file=output)
        print('\tDEST2', prop['dest2'], file=output)
        print('\tDEST3', prop['dest3'], file=output)
        print('\tDEST4', prop['dest4'], file=output)
        print('\tDEST5', prop['dest5'], file=output)
        print('\tDEST6', prop['dest6'], file=output)
        print('\tDEST7', prop['dest7'], file=output)
        print('\tDEST8', prop['dest8'], file=output)
        print('\tDEST9', prop['dest9'], file=output)
        print('\tDEST10', prop['dest10'], file=output)
        print('\tDEST11', prop['dest11'], file=output)
        print('\tDEST12', prop['dest12'], file=output)
    else:
        prop = cast(SuperRoomProperty, prop)
        print(
            '\tSUPER_ROOM',
            prop['srid'],
            prop['x'],
            prop['y'],
            prop['z'],
            file=output,
        )
        print('\tEXITS', ' '.join(str(ex) for ex in prop['exits']), file=output)


def write_property_text(
    prop: 'Property',
    output: IO[str],
    resolve: 'Callable[[Param], str]',
) -> None:
    print(f'==> {prop["ptype"].name}', file=output)
    if prop['ptype'] == ItemType.OBJECT:
        write_object_property_text(prop, output, resolve)
    elif prop['ptype'] == ItemType.ROOM:
        write_room_property_text(prop, output, resolve)
    elif prop['ptype'] == ItemType.INHERIT:
        print('\tITEM', prop['item'], file=output)
    elif prop['ptype'] == ItemType.USERFLAG:
        print('\t1', prop['flag1'], file=output)
        print('\t2', prop['flag2'], file=output)
        print('\t3', prop['flag3'], file=output)
        print('\t4', prop['flag4'], file=output)
        if prop.get('game') == GameID.elvira1:
            prop = cast(ElviraUserFlagProperty, prop)
            print('\t5', prop['flag5'], file=output)
            print('\t6', prop['flag6'], file=output)
            print('\t7', prop['flag7'], file=output)
            print('\t8', prop['flag8'], file=output)
            print('\tITEM1', prop['item1'], file=output)
            print('\tITEM2', prop['item2'], file=output)
            print('\tITEM3', prop['item3'], file=output)
            print('\tITEM4', prop['item4'], file=output)
    elif prop['ptype'] == ItemType.CONTAINER:
        print('\tVOLUME', prop['volume'], file=output)
        print('\tFLAGS', prop['flags'], file=output)
        # TODO: show actual flags values, from AberMUD V source:
        #       CO_SOFT		1	/* Item has size increased by contents  */
        #       CO_SEETHRU	2	/* You can see into the item		*/
        #       CO_CANPUTIN	4	/* For PUTIN action			*/
        #       CO_CANGETOUT	8	/* For GETOUT action			*/
        #       CO_CLOSES	16	/* Not state 0 = closed			*/
        #       CO_SEEIN	32	/* Container shows contents by		*/
    elif prop['ptype'] == ItemType.SUPER_ROOM:
        write_super_room_genexit_property_text(prop, output, resolve)
    elif prop['ptype'] == ItemType.CHAIN:
        print('\tITEM', prop['item'], file=output)
    else:
        raise ValueError(prop)


def write_objects(
    objects: 'Sequence[Item]',
    output: 'FilePath',
    all_strings: 'Mapping[int, str]',
    encoding: 'EncodeSettings',
) -> None:
    output = Path(output)
    resolve = partial(resolve_strings, all_strings)
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
                    obj['actor_table'],
                    obj['item_class'],
                    obj['properties_init'],
                ),
                file=output_file,
            )
            if obj['name'] is not None:
                print(
                    '\tNAME',
                    obj['name'].value,
                    '//',
                    resolve(obj['name']),
                    file=output_file,
                )
            perception = obj.get('perception')
            if perception is not None:
                print(
                    '\tPERCEPTION',
                    perception,
                    file=output_file,
                )
            action_table = obj.get('action_table')
            if action_table is not None:
                print(
                    '\tACTION_TABLE',
                    action_table,
                    file=output_file,
                )
            users = obj.get('users')
            if users is not None:
                print(
                    '\tUSERS',
                    users,
                    file=output_file,
                )
            for prop in obj['properties']:
                write_property_text(prop, output_file, resolve)


def load_objects(objects_file: IO[str], game: 'GameID') -> 'Iterator[Item]':
    objects_data = objects_file.read()
    blank, *defs = objects_data.split('== DEFINE')
    assert not blank, blank
    for do in defs:
        rlidx, *props = do.split('==> ')
        lidx = [int(x) for x in rlidx.split('==')[0].split() if x]
        additional = rlidx.split('==')[1].rstrip('\n')
        extra: dict[str, Param | int] = {}
        if additional:
            aprops = dict(
                x.split(' //')[0].split(maxsplit=1)
                for x in additional.strip().split('\n\t')
            )
            name = aprops.pop('NAME', None)
            if name is not None:
                extra['name'] = Param('T', int(name))

            perception = aprops.pop('PERCEPTION', None)
            if perception is not None:
                extra['perception'] = int(perception)

            action_table = aprops.pop('ACTION_TABLE', None)
            if action_table is not None:
                extra['action_table'] = int(action_table)

            users = aprops.pop('USERS', None)
            if users is not None:
                extra['users'] = int(users)

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
                        'actor_table',
                        'item_class',
                        'properties_init',
                        'properties',
                    ),
                    (*lidx, list(parse_props(props, game=game))),
                    strict=True,
                ),
                **extra,
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
                samples: Iterable[int] | None = soundmap.get(idx, None)
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


def index_texts(basedir: Path) -> 'Iterator[tuple[str, int]]':
    yield from index_text_files(basedir / 'STRIPPED.TXT')


def rewrite_tables(tables: 'Iterable[Table]') -> bytes:
    if not tables:
        return b''
    return b'\0\0' + b'\0\0'.join(bytes(tab) for tab in tables) + b'\0\1'


def compile_tables(
    scr_file: IO[str],
    parser: Parser,
    text_files: list[tuple[str, int]],
) -> 'Iterator[tuple[str, tuple[Sequence[Table], SubRanges]]]':
    script_data = scr_file.read()
    blank, *tables = script_data.split('== FILE')
    assert not blank, blank
    line_number = 1
    min_key = max_key = BASE_MIN
    for table in tables:
        fidx, *lines = table.split('== TABLE ')
        fname = fidx.split()[0]
        subs = fidx.split()[1:]
        psubs: tuple[tuple[int, int], ...] = ()
        if subs != ['~']:
            for sub in subs:
                min_key, max_key = (int(x) for x in sub.split(':', maxsplit=1))
                psubs += ((min_key, max_key),)
        tname = fname.replace('TABLES', 'TEXT')
        max_key = next((key for name, key in text_files if name == tname), max_key)
        assert parser.game is not None
        text_range = (
            # TODO: Narrow down the range for older games
            range(BASE_MIN, WORD_MASK + 1)
            if parser.game <= GameID.waxworks
            else range(min_key, max_key)
        )
        parsed: list[Table] = []
        try:
            parsed.extend(
                parse_tables(
                    lines,
                    parser,
                    text_range,
                ),
            )
        except ParseError as exc:
            exc.file = fname
            exc.line_number += line_number + fidx.count('\n')
            exc.show(scr_file.name)
            raise
        min_key = max_key
        line_number += table.count('\n')
        # TODO: Check if ranges are overlapping
        yield fname, (list(validate_sub_ranges(parsed, psubs)), psubs)


class TableOutOfRangeError(ValueError):
    def __init__(self, table_number: int, subs: 'SubRanges') -> None:
        super().__init__(
            f'table {table_number} is out of range, '
            f'valid ranges are: {", ".join(f"{mn}:{mx}" for mn, mx in subs)}',
        )


def validate_sub_ranges(
    tables: 'Iterable[Table]',
    subs: 'SubRanges' = (),
) -> 'Iterator[Table]':
    if not subs:
        # validation is not needed
        yield from tables
        return
    ranges = (range(sub[0], sub[1] + 1) for sub in subs)
    crange = next(ranges)
    for tab in tables:
        # when a table goes out of range, skip to the next range
        while tab.number not in crange:
            try:
                crange = next(ranges)
            except StopIteration:
                # no more ranges so table number is invalid
                raise TableOutOfRangeError(tab.number, subs) from None
        yield tab
        # make sure table numbers are sorted inside each range
        crange = range(tab.number, crange.stop)


def dump_tables(
    stream: IO[bytes],
    gparser: Parser,
    all_strings: 'Mapping[int, str]',
    subs: 'SubRanges' = (),
    *,
    soundmap: dict[int, set[int]] | None = None,
) -> 'Iterator[str]':
    tables = load_tables(stream, gparser, soundmap=soundmap)
    for tab in validate_sub_ranges(tables, subs):
        yield f'== TABLE {tab.number}'
        yield from tab.resolve(all_strings)


def write_scripts(
    subtables: 'Iterable[tuple[SubRanges, str, bytes]]',
    scr_file: IO[str],
    gparser: Parser,
    all_strings: 'Mapping[int, str]',
    *,
    soundmap: dict[int, set[int]] | None = None,
) -> None:
    for subs, fname, content in subtables:
        with io.BytesIO(content) as stream:
            subranges = ' '.join(f'{mn}:{mx}' for mn, mx in subs) if subs else '~'
            print('== FILE', fname, subranges, file=scr_file)
            lines = dump_tables(
                stream,
                gparser,
                all_strings,
                subs,
                soundmap=soundmap,
            )
            for line in lines:
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
    path: Path
    crypt: str | None
    output: Path
    extract: Path | None
    game: str | None
    script: Path | None
    items: Path
    voice: 'Sequence[str]'
    rebuild: bool
    unicode: bool
    voice_base: Path = Path('voices')


class OptionalFileAction(argparse.Action):
    def __init__(
        self,
        option_strings: 'Sequence[str]',
        dest: str,
        default_path: Path,
        **kwargs: Any,
    ) -> None:
        self.default_path = default_path
        super().__init__(option_strings, dest, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: 'str | Sequence[Any] | None',
        option_string: str | None = None,
    ) -> None:
        if values is None:
            setattr(namespace, self.dest, self.default_path)
        else:
            setattr(namespace, self.dest, values)


def menu(args: 'Sequence[str] | None' = None) -> CLIParams:
    parser = argparse.ArgumentParser(
        description='Process resources for Simon the Sorcerer.',
    )
    parser.add_argument(
        'path',
        type=Path,
        help='Path to the game directory',
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
        choices=known_variants.keys(),
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
        nargs='?',
        type=Path,
        action=OptionalFileAction,
        default=None,
        default_path=Path('scripts.txt'),
        help='File to output game scripts to (default: scripts.txt)',
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
    game: GameID
    detection: DetectionEntry
    archive: 'MutableMapping[str, bytes]'
    text_files: 'Sequence[tuple[str, int]]'
    filenames: 'Sequence[str]'
    gbi: 'GameBasefileInfo'
    packed: str | None

    def __init__(self, path: 'FilePath', variant: str | None = None) -> None:
        self.basedir = Path(path)
        detection = (
            known_variants[variant]
            if variant
            else auto_detect_game_from_filenames(self.basedir)
        )
        self.detection = detection
        self.game = detection.game
        self.script = detection.script
        self.text_files = list(index_texts(self.basedir))
        self.packed = detection.archive

        self.filenames = list(get_packed_filenames(detection.archive, self.basedir))
        self.basefile = detection.basefile
        extra = bytearray()
        if detection.archive is None:
            self.archive = DirectoryBackedArchive(self.basedir, allowed=self.filenames)
        else:
            self.archive = {
                fname: content
                for _, fname, content in read_gme(
                    self.filenames,
                    self.basedir / detection.archive,
                    extra,
                )
            }

        self.extra = bytes(extra)

        with (self.basedir / self.basefile).open('rb') as game_file:
            self.gbi = read_gamepc(game_file)
            assert game_file.read() == b''

    def parser(self) -> Parser:
        return Parser(
            optables[self.game][self.script],
            text_mask=(0xFFFF0000 if self.game <= GameID.simon1 else 0),
            game=self.game,
        )


def extract(
    game: GameInfo,
    args: CLIParams,
    oc: OutputConfig,
    voices: 'Iterable[Path]',
) -> None:
    if args.extract is not None and game.packed:
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
            defaultdict(set) if game.script == 'talkie' else None
        )
        gparser = game.parser()
        index_tables = (
            index_table_files_elvira
            if game.game <= GameID.elvira2
            else index_table_files
        )
        tables = list(index_tables(game.basedir / 'XTBLLIST')) + list(
            index_tables(game.basedir / 'TBLLIST')
        )

        all_strings = flatten_strings(strings)

        with io.BytesIO(game.gbi.tables) as stream:
            item_count = (
                game.gbi.total_item_count
                if game.game <= GameID.elvira2
                else game.gbi.item_count
            )
            objects = read_objects(
                stream,
                item_count,
                game=game.game,
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
            ((), game.basefile, memoryview(game.gbi.tables)[table_pos:]),
            *((subs, fname, game.archive[fname]) for fname, subs in tables),
        ]

        with args.script.open('w', **oc.output_encoding) as scr_file:
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
    if args.extract is not None and game.packed:
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
        gparser = game.parser()
        with args.items.open('r', **oc.output_encoding) as objects_file:
            objects = list(load_objects(objects_file, game=game.game))

        with args.script.open('r', **oc.output_encoding) as scr_file:
            btables = dict(compile_tables(scr_file, gparser, text_files))

        base_tables = btables.pop(game.basefile)
        with io.BytesIO(game.gbi.tables) as tbl_file:
            item_count = (
                game.gbi.total_item_count
                if game.game <= GameID.elvira2
                else game.gbi.item_count
            )
            _orig_objects = read_objects(tbl_file, item_count, game=game.game)
            _pref = game.gbi.tables[: tbl_file.tell()]
            _orig = list(load_tables(tbl_file, gparser))
            leftover = tbl_file.read()

        objects_pref = write_objects_bytes(objects, game=game.game)
        parsed, subs = base_tables
        tables_data = objects_pref + rewrite_tables(parsed) + leftover

        tables_index: Mapping[str, dict[str, SubRanges]] = defaultdict(dict)
        for fname, ftables in btables.items():
            parsed, subs = ftables
            idx_name = 'XTBLLIST' if 'XTABLE' in fname else 'TBLLIST'
            tables_index[idx_name][fname] = subs
            game.archive[fname] = rewrite_tables(parsed)

        compose_tables_index(tables_index, game.game, game.archive)

    extra = game.extra
    if game.packed:
        write_gme(
            merge_packed([game.archive[afname] for afname in game.filenames]),
            game.packed,
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

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: Given path '{path}' does not exists.", file=error_stream)
        sys.exit(1)

    if not path.is_dir():
        print(f"ERROR: Given path '{path}' is not a directory.", file=error_stream)
        sys.exit(1)

    try:
        game = GameInfo(args.path, args.game)
    except ValueError as exc:
        print(f'ERROR: {exc}', file=error_stream)
        sys.exit(1)

    print(f'Detected as {game.detection}', file=error_stream)

    voices = sorted(
        set(chain.from_iterable(game.basedir.glob(r) for r in args.voice)),
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
