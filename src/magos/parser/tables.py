import io
from typing import (
    IO,
    TYPE_CHECKING,
)

from magos.detection import (
    GameID,
)
from magos.parser.params import (
    BASE_MIN,
    WORD_MASK,
)
from magos.parser.script import (
    ParseError,
    Parser,
    load_tables,
    parse_tables,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

    from magos.gmepack import SubRanges
    from magos.parser.params import Param
    from magos.parser.script import Table


class TableOutOfRangeError(ValueError):
    def __init__(self, table_number: int, subs: 'SubRanges') -> None:
        super().__init__(
            f'table {table_number} is out of range, '
            f'valid ranges are: {", ".join(f"{mn}:{mx}" for mn, mx in subs)}',
        )


def rewrite_tables(tables: 'Iterable[Table]') -> bytes:
    if not tables:
        return b''
    return b'\0\0' + b'\0\0'.join(bytes(tab) for tab in tables) + b'\0\1'


def validate_sub_ranges(
    tables: 'Iterable[Table]',
    subs: 'SubRanges' = (),
) -> 'Iterator[Table]':
    if not subs:
        # validation is not needed
        yield from tables
        return
    ranges = (range(sub[0], sub[1] + 1) for sub in subs)
    crange = next(ranges, None)
    assert crange is not None
    for tab in tables:
        # when a table goes out of range, skip to the next range
        while tab.number not in crange:
            crange = next(ranges, None)
            if crange is None:
                # no more ranges so table number is invalid
                raise TableOutOfRangeError(tab.number, subs)
        yield tab
        # make sure table numbers are sorted inside each range
        crange = range(tab.number, crange.stop)


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


def dump_tables(
    stream: IO[bytes],
    gparser: Parser,
    resolve: 'Callable[[Param], str]',
    subs: 'SubRanges' = (),
    *,
    soundmap: dict[int, set[int]] | None = None,
) -> 'Iterator[str]':
    tables = load_tables(stream, gparser, soundmap=soundmap)
    for tab in validate_sub_ranges(tables, subs):
        yield f'== TABLE {tab.number}'
        yield from tab.write_text(resolve)


def write_scripts(
    subtables: 'Iterable[tuple[SubRanges, str, bytes]]',
    scr_file: IO[str],
    gparser: Parser,
    resolve: 'Callable[[Param], str]',
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
                resolve,
                subs,
                soundmap=soundmap,
            )
            for line in lines:
                print(line, file=scr_file)
