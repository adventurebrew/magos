import struct
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    TextIO,
)

from magos.detection import GameID
from magos.parser.params import (
    BASE_MIN,
    BYTE_MASK,
    WORD_MASK,
    Param,
    ParamElvira,
)
from magos.stream import (
    read_uint16be,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

CMD_EOL = 10000


MIA_OP = 'UNKNOWN_OP'
ops_mia: Counter[int] = Counter()


@dataclass
class Command:
    opcode: int
    cmd: str | None
    args: Sequence[Param]

    def __post_init__(self) -> None:
        if self.cmd is None:
            ops_mia.update({self.opcode: 1})

    def __str__(self) -> str:
        cmd = f'(0x{self.opcode:02x}) {self.cmd or MIA_OP}'
        return ' '.join(str(x) for x in (cmd, *self.args))

    def resolve(self, all_strings: 'Mapping[int, str]') -> str:
        cmd = f'(0x{self.opcode:02x}) {self.cmd or MIA_OP}'
        comments = ''.join(x.resolve(all_strings) for x in self.args)
        if comments:
            comments = f' // {comments}'
        return ' '.join(str(x) for x in (cmd, *self.args)) + comments

    def __bytes__(self) -> bytes:
        return bytes([self.opcode]) + b''.join(bytes(p) for p in self.args)


class CommandElvira(Command):
    def __bytes__(self) -> bytes:
        return self.opcode.to_bytes(2, byteorder='big', signed=False) + b''.join(
            bytes(p) for p in self.args
        )


@dataclass
class Line:
    parts: Sequence[Command]

    def __str__(self) -> str:
        inlined = [str(part) for part in self.parts]
        joined = '\n\t'.join(inlined)
        return f'==> {joined}'

    def resolve(self, all_strings: 'Mapping[int, str]') -> str:
        inlined = [part.resolve(all_strings) for part in self.parts]
        joined = '\n\t'.join(inlined)
        return f'==> {joined}'

    def __bytes__(self) -> bytes:
        return b''.join(bytes(cmd) for cmd in self.parts) + b'\xff'


@dataclass
class LineElvira(Line):
    def __bytes__(self) -> bytes:
        return b''.join(bytes(cmd) for cmd in self.parts) + CMD_EOL.to_bytes(
            2, byteorder='big', signed=False
        )


@dataclass
class Table:
    number: int
    parts: 'Sequence[Line | ObjDefintion]'

    def resolve(
        self,
        all_strings: 'Mapping[int, str]',
    ) -> 'Iterator[str]':
        yield from (part.resolve(all_strings) for part in self.parts)

    def __bytes__(self) -> bytes:
        out = bytearray(self.number.to_bytes(2, byteorder='big', signed=False))
        it = iter(self.parts)
        for seq in it:
            out += b'\0\0'
            if isinstance(seq, ObjDefintion):
                out += bytes(seq) + bytes(next(it))
            else:
                out += bytes(seq)
        return bytes(out + b'\0\1')


@dataclass
class ObjDefintion:
    verb: int
    noun1: int
    noun2: int

    def resolve(self, all_strings: 'Mapping[int, str]') -> str:
        return f'==> DEF: {self.verb:=} {self.noun1:=} {self.noun2:=}'

    def __bytes__(self) -> bytes:
        return (
            self.verb.to_bytes(2, byteorder='big', signed=False)
            + self.noun1.to_bytes(2, byteorder='big', signed=False)
            + self.noun2.to_bytes(2, byteorder='big', signed=False)
        )


def decode_script(
    stream: IO[bytes],
    parser: 'Parser',
    soundmap: dict[int, set[int]] | None = None,
) -> 'Iterator[Command]':
    (realize_params_func, command_type, sentinel, opsize) = (
        (ParamElvira.from_bytes, CommandElvira, CMD_EOL, 2)
        if parser.game == GameID.elvira1
        else (Param.from_bytes, Command, BYTE_MASK, 1)
    )

    while True:
        pos = stream.tell()
        opcode = int.from_bytes(stream.read(opsize), byteorder='big', signed=False)
        if opcode == sentinel:
            break
        cmd, params = parser.optable[opcode]
        args = tuple(realize_params_func(params, stream, parser.text_mask))
        c = command_type(opcode, cmd, args)
        npos = stream.tell()
        yield c
        stream.seek(pos)
        assert stream.read(npos - pos) == bytes(c)
        if soundmap is not None and 'S' in params:
            assert 'T' in params, params
            soundmap[int(args[params.index('T')].value) & WORD_MASK].add(
                int(args[params.index('S')].value),
            )


def load_table(
    stream: IO[bytes],
    number: int,
    parser: 'Parser',
    soundmap: dict[int, set[int]] | None = None,
) -> 'Iterator[Line | ObjDefintion]':
    line_type = LineElvira if parser.game == GameID.elvira1 else Line
    while True:
        if read_uint16be(stream) != 0:
            break

        if number == 0 or parser.game == GameID.elvira1:
            verb = read_uint16be(stream)
            noun1 = read_uint16be(stream)
            noun2 = read_uint16be(stream)
            yield ObjDefintion(verb, noun1, noun2)

        yield line_type(list(decode_script(stream, parser, soundmap=soundmap)))


def load_tables(
    stream: IO[bytes],
    parser: 'Parser',
    soundmap: dict[int, set[int]] | None = None,
) -> 'Iterator[Table]':
    while True:
        try:
            if read_uint16be(stream) != 0:
                break
        except struct.error:
            break

        number = read_uint16be(stream)
        yield Table(number, list(load_table(stream, number, parser, soundmap=soundmap)))


@dataclass
class Parser:
    optable: 'Mapping[int, tuple[str | None, str]]' = field(repr=False)
    text_mask: int = 0
    game: GameID | None = None


def tokenize_cmds(
    cmds: 'Iterable[str]',
    parser: 'Parser',
) -> 'Iterable[tuple[int, str, Sequence[str]]]':
    keywords = {command: op for op, (command, _) in parser.optable.items()}
    key = None
    command = None
    params = []
    for token in cmds:
        if token.startswith('(0x') and token.endswith(')'):
            if key is not None:
                params.append(key)
            key = token
        elif token in keywords:
            if command is not None:
                yield (keywords[command], command, params)
                params = []
            command = token
            # Check if current keyword matches key
            if key is not None and keywords[command] != int(key.strip('()'), 16):
                raise OpcodeCommandMismatchError(key, keywords[command], command)
            key = None
        else:
            if key is not None:
                params.append(key)
            params.append(token)
            key = None
            if command is None:
                raise UnrecognizedCommandError(token)
    if command is not None:
        yield (keywords[command], command, params)


class ParseError(ValueError):
    message: str
    command: str
    sargs: Sequence[str]
    line_number: int
    linetab: str
    file: str | None = None
    tidx: int | None = None
    line: int | None = None
    stream: TextIO

    def __init__(
        self,
        message: str,
        command: str,
        sargs: Sequence[str],
        *rest: Any,
    ) -> None:
        super().__init__(message, command, sargs, *rest)
        self.message = message
        self.command = command
        self.sargs = sargs
        self.stream = sys.stderr

    def highlight(self, linetab: str) -> str:
        focus = ' '.join([self.command, *self.sargs])
        return linetab.replace(focus, f'-> {focus} <-', 1)

    def show(self, scr_file: str) -> None:
        print('ERROR: Cannot parse scripts file at', file=self.stream)
        print(
            '\n'.join(
                [
                    f'  FILE: {self.file}',
                    f'  TABLE: {self.tidx}',
                    f'  LINE: {self.line}',
                ],
            ),
            file=self.stream,
        )
        print(
            f'Block starts at {scr_file}:{self.line_number}:',
            file=self.stream,
        )
        print(self.highlight(self.linetab), file=self.stream)
        print(self.message, file=self.stream)


class UnrecognizedCommandError(ParseError):
    def __init__(self, command: str) -> None:
        super().__init__(f'unrecognized command name {command}', command, [])


class OpcodeCommandMismatchError(ParseError):
    def __init__(self, key: str, expected: int, command: str) -> None:
        super().__init__(
            f'opcode for {command} should have been (0x{expected:02x}) but found {key}',
            command,
            [],
        )
        self.key = key
        self.expected = expected

    def highlight(self, linetab: str) -> str:
        focus = f'{self.key} {self.command}'
        return linetab.replace(focus, f'-> {focus} <-', 1)


class ParameterCountMismatchError(ParseError):
    params: str

    def __init__(self, command: str, args: Sequence[str], params: str) -> None:
        stripped = params.rstrip()
        joined = ' '.join(args)
        super().__init__(
            (
                f'{command} expects {len(stripped)} parameters'
                f' of types {stripped}'
                f' but {len(args)} given: {joined}'
            ),
            command,
            args,
        )
        self.params = params


class ArgumentParseError(ParseError):
    params: str

    def __init__(
        self,
        command: str,
        args: Sequence[str],
        params: str,
        cause: ValueError | None = None,
    ) -> None:
        stripped = params.rstrip()
        joined = ' '.join(args)
        super().__init__(
            (
                f'could not parse given arguments {joined} as types {stripped}'
                + (f': {cause}' if cause else '')
            ),
            command,
            args,
        )
        self.params = params


class InvalidTextReferenceError(ParseError):
    text_id: int

    def __init__(
        self,
        command: str,
        args: Sequence[str],
        text_id: int,
        text_range: range,
    ) -> None:
        super().__init__(
            (
                f'text {text_id} is outside of expected range for current file:'
                f' [{text_range.start}..{text_range.stop})\n'
                'try moving this text to a different file or making it global'
            ),
            command,
            args,
        )
        self.text_id = text_id

    def highlight(self, linetab: str) -> str:
        focus = str(self.text_id)
        return linetab.replace(focus, f'-> {focus} <-', 1)


def parse_cmds(
    cmds: 'Iterable[str]',
    parser: 'Parser',
    text_range: range,
) -> 'Iterator[Command]':
    (parse_args_func, command_type) = (
        (ParamElvira.from_parsed, CommandElvira)
        if parser.game == GameID.elvira1
        else (Param.from_parsed, Command)
    )
    for op, command, args in tokenize_cmds(cmds, parser):
        ename, params = parser.optable[op]
        assert command == ename, (command, ename)
        if len(args) != len(params.rstrip(' ')):
            raise ParameterCountMismatchError(command, args, params)
        try:
            parsed = tuple(parse_args_func(iter(args), params, parser.text_mask))
        except ValueError as exc:
            raise ArgumentParseError(command, args, params, exc) from exc
        for p in parsed:
            if p.ptype != 'T':
                continue
            text_ref = p.value & ~p.mask
            if text_ref >= BASE_MIN and text_ref not in text_range:
                raise InvalidTextReferenceError(command, args, text_ref, text_range)
        yield command_type(op, command, parsed)


def parse_lines(
    lidx: int,
    tabs: 'Iterable[str]',
    parser: 'Parser',
    text_range: range,
) -> 'Iterator[Line | ObjDefintion]':
    line_type = LineElvira if parser.game == GameID.elvira1 else Line

    line_number = 0
    for bidx, tab in enumerate(tabs, start=1):
        if tab.startswith('DEF: '):
            assert lidx == 0 or parser.game == GameID.elvira1, lidx
            yield ObjDefintion(*(int(x) for x in tab.split()[1:]))
            line_number += tab.count('\n')
            continue
        cmds = ''.join(x.split('//')[0] for x in tab.split('\n')).split()
        try:
            yield line_type(list(parse_cmds(cmds, parser, text_range)))
        except ParseError as exc:
            exc.line_number = line_number
            exc.line = bidx
            exc.linetab = '==>\t' + tab
            raise
        line_number += tab.count('\n')


def parse_tables(
    lines: 'Iterable[str]',
    parser: 'Parser',
    text_range: range,
) -> 'Iterator[Table]':
    line_number = 0
    for line in lines:
        rlidx, *tabs = line.split('==> ')
        tidx = int(rlidx.split('==')[0])
        try:
            yield Table(tidx, list(parse_lines(tidx, tabs, parser, text_range)))
        except ParseError as exc:
            exc.tidx = tidx
            exc.line_number += line_number + rlidx.count('\n')
            raise
        line_number += line.count('\n')
