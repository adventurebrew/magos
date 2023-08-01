import struct
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Literal,
    TextIO,
    TypedDict,
    cast,
)

from magos.stream import (
    read_uint16be,
    read_uint32be,
    write_uint16be,
    write_uint32be,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

DWORD_MASK = 0xFFFFFFFF
WORD_MASK = 0xFFFF
BYTE_MASK = 0xFF

BASE_MIN = 0x8000


def read_item(stream: IO[bytes]) -> int:
    val = read_uint32be(stream)
    return 0 if val == DWORD_MASK else val + 2


def write_item(num: int) -> bytes:
    return write_uint32be(DWORD_MASK if num == 0 else num - 2)


class ItemType(IntEnum):
    ROOM = 1
    OBJECT = 2
    PLAYER = 3
    SUPER_ROOM = 4
    CHAIN = 8
    USERFLAG = 9
    INHERIT = 255


class PropertyType(IntEnum):
    DESCRIPTION = 0
    SIZE = 1
    WEIGHT = 2
    VOLUME = 3
    ICON = 4
    MENU = 7
    NUMBER = 8
    VOICE = 9

    FLAGS = 17


class DoorState(IntEnum):
    OPEN = 1
    CLOSED = 2
    LOCKED = 3


class Exit(TypedDict):
    exit_to: int
    status: DoorState


class RoomProperty(TypedDict):
    ptype: Literal[ItemType.ROOM]
    table: int
    exits: Sequence[Exit | None]


def read_room(stream: IO[bytes]) -> RoomProperty:
    table = read_uint16be(stream)
    exit_states = read_uint16be(stream)

    exits: list[Exit | None] = []

    for _ in range(6):
        ex: Exit | None = None
        if exit_states & 3 != 0:
            ex = Exit(
                exit_to=read_item(stream),
                status=DoorState(exit_states & 3),
            )
            assert ex['exit_to'] != 0
        exits.append(ex)
        exit_states >>= 2

    return RoomProperty(
        ptype=ItemType.ROOM,
        table=table,
        exits=exits,
    )


class ObjectProperty(TypedDict):
    ptype: Literal[ItemType.OBJECT]
    params: 'dict[PropertyType, int | Param]'
    name: 'Param'


def read_object_property(
    stream: IO[bytes],
    soundmap: dict[int, set[int]] | None = None,
) -> ObjectProperty:
    params: 'dict[PropertyType, int | Param]' = {}

    flags = read_uint32be(stream)

    text = None
    if flags & 1:
        text = Param('T', read_uint32be(stream))
        params[PropertyType(0)] = text

    for n in range(1, 16):
        if flags & (1 << n) != 0:
            params[PropertyType(n)] = read_uint16be(stream)

    flags >>= 16
    if flags:
        params[PropertyType.FLAGS] = flags

    if soundmap is not None and text is not None:
        voice = params.get(PropertyType.VOICE)
        if voice is not None:
            assert isinstance(voice, int)
            soundmap[text.value].add(voice)
    name = Param('T', read_uint32be(stream))

    return ObjectProperty(
        ptype=ItemType.OBJECT,
        params=params,
        name=name,
    )


class UserFlagProperty(TypedDict):
    ptype: Literal[ItemType.USERFLAG]
    flag1: int
    flag2: int
    flag3: int
    flag4: int


class InheritProperty(TypedDict):
    ptype: Literal[ItemType.INHERIT]
    item: int


Property = RoomProperty | ObjectProperty | UserFlagProperty | InheritProperty


class Item(TypedDict):
    adjective: int
    noun: int
    state: int
    next_item: int
    child: int
    parent: int
    unk: int
    item_class: int
    properties_init: int
    properties: Sequence[Property]


def read_properties(
    stream: IO[bytes],
    ptype: ItemType,
    soundmap: dict[int, set[int]] | None = None,
) -> Property:
    if ptype == ItemType.ROOM:
        return read_room(stream)
    if ptype == ItemType.OBJECT:
        return read_object_property(stream, soundmap=soundmap)
    if ptype == ItemType.PLAYER:
        raise NotImplementedError('KEY_PLAYER')
    if ptype == ItemType.SUPER_ROOM:
        raise NotImplementedError('KEY_SUPER_ROOM')
    if ptype == ItemType.CHAIN:
        raise NotImplementedError('KEY_CHAIN')
    if ptype == ItemType.USERFLAG:
        return UserFlagProperty(
            ptype=ItemType.USERFLAG,
            flag1=read_uint16be(stream),
            flag2=read_uint16be(stream),
            flag3=read_uint16be(stream),
            flag4=read_uint16be(stream),
        )
    if ptype == ItemType.INHERIT:
        return InheritProperty(
            ptype=ItemType.INHERIT,
            item=read_item(stream),
        )
    raise NotImplementedError(ptype)


def read_objects(
    stream: IO[bytes],
    item_count: int,
    soundmap: dict[int, set[int]] | None = None,
) -> Sequence[Item]:
    return [read_object(stream, soundmap=soundmap) for i in range(2, item_count)]


def read_object(
    stream: IO[bytes],
    soundmap: dict[int, set[int]] | None = None,
) -> Item:

    adjective = read_uint16be(stream)
    noun = read_uint16be(stream)
    state = read_uint16be(stream)
    next_item = read_item(stream)
    child = read_item(stream)
    parent = read_item(stream)
    unk = read_uint16be(stream)
    item_class = read_uint16be(stream)
    properties_init = read_uint32be(stream)
    properties = []
    props = properties_init
    while props:
        props = read_uint16be(stream)
        if props != 0:
            ptype = ItemType(props)
            properties.append(read_properties(stream, ptype, soundmap=soundmap))
    return Item(
        adjective=adjective,
        noun=noun,
        state=state,
        next_item=next_item,
        child=child,
        parent=parent,
        unk=unk,
        item_class=item_class,
        properties_init=properties_init,
        properties=properties,
    )


def write_room(prop: RoomProperty) -> bytes:
    exit_states = 0
    sout = bytearray()
    for ex in prop['exits'][::-1]:
        exit_states <<= 2
        if ex is not None:
            assert ex['status'] != 0, ex
            sout = bytearray(write_item(ex['exit_to']) + sout)
            exit_states |= ex['status']
    return write_uint16be(prop['table']) + write_uint16be(exit_states) + bytes(sout)


def write_object_property(prop: ObjectProperty) -> bytes:
    sout = bytearray()
    flags = cast(int, prop['params'].pop(PropertyType.FLAGS, 0)) << 16
    for key in PropertyType:
        val = prop['params'].pop(key, None)
        if val is not None:
            flags |= 2**key
            sout += (
                write_uint32be(cast(Param, val).value)
                if key == 0
                else write_uint16be(cast(int, val))
            )
    assert not prop['params'], prop['params']
    return write_uint32be(flags) + bytes(sout) + write_uint32be(prop['name'].value)


def write_user_flag(prop: UserFlagProperty) -> bytes:
    return (
        write_uint16be(prop['flag1'])
        + write_uint16be(prop['flag2'])
        + write_uint16be(prop['flag3'])
        + write_uint16be(prop['flag4'])
    )


def write_objects_bytes(objects: Sequence[Item]) -> bytes:
    output = bytearray()
    for obj in objects:
        output += write_uint16be(obj['adjective'])
        output += write_uint16be(obj['noun'])
        output += write_uint16be(obj['state'])
        output += write_item(obj['next_item'])
        output += write_item(obj['child'])
        output += write_item(obj['parent'])
        output += write_uint16be(obj['unk'])
        output += write_uint16be(obj['item_class'])
        output += write_uint32be(obj['properties_init'])
        for prop in obj['properties']:
            output += write_uint16be(prop['ptype'])
            if prop['ptype'] == ItemType.ROOM:
                output += write_room(prop)
            elif prop['ptype'] == ItemType.OBJECT:
                output += write_object_property(prop)
            elif prop['ptype'] == ItemType.INHERIT:
                output += write_item(prop['item'])
            elif prop['ptype'] == ItemType.USERFLAG:
                output += write_user_flag(prop)
            else:
                raise ValueError(prop)
        if obj['properties']:
            output += write_uint16be(0)
    return bytes(output)


@dataclass
class Param:
    ptype: str
    value: Any
    mask: int = 0

    def __str__(self) -> str:
        if self.ptype == 'T' and self.value > 0:
            return str(self.value & ~self.mask)
        return str(self.value)

    def resolve(self, all_strings: 'Mapping[int, str]') -> str:
        if self.ptype == 'T':
            msg = None
            num = self.value & WORD_MASK
            if num != WORD_MASK:
                msg = all_strings.get(self.value & WORD_MASK, 'MISSING STRING')
            return f'{{{msg}}}'
        return ''

    def __bytes__(self) -> bytes:
        if self.ptype == 'T':
            assert isinstance(self.value, int)
            rtypes = {-1: 0, -3: 3}
            special = rtypes.get(self.value, 1)
            rtype = special.to_bytes(2, byteorder='big', signed=False)
            value = b''
            if special == 1:
                value = self.value.to_bytes(4, byteorder='big', signed=False)
            return rtype + value

        if self.ptype == 'B':
            return (
                bytes([BYTE_MASK, *self.value])
                if isinstance(self.value, list)
                else bytes([self.value])
            )

        if self.ptype == 'I':
            special_items = {
                '$1': 1,  # SUBJECT_ITEM
                '$2': 3,  # OBJECT_ITEM
                '$ME': 5,  # ME_ITEM
                '$AC': 7,  # ACTOR_ITEM
                '$RM': 9,  # ITEM_A_PARENT
            }
            special = special_items.get(self.value, 0)
            rtype = special.to_bytes(2, byteorder='big', signed=False)
            value = b''
            if special == 0:
                num = int(self.value[1:-1]) - 2
                value = num.to_bytes(4, byteorder='big', signed=False)
            return rtype + value

        if self.ptype in {
            'v',
            'p',
            'n',
            'a',
            'S',
            'N',
        }:
            assert isinstance(self.value, int)
            return self.value.to_bytes(2, byteorder='big', signed=False)

        raise ValueError(self.ptype)


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
        return b''.join(bytes(cmd) for cmd in self.parts) + b'\xFF'


@dataclass
class Table:
    number: int
    parts: 'Sequence[Line | ObjDefintion]'

    def resolve(self, all_strings: 'Mapping[int, str]') -> 'Iterator[str]':
        yield f'== LINE {self.number}=='
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


def load_table(
    stream: IO[bytes],
    number: int,
    parser: 'Parser',
    soundmap: dict[int, set[int]] | None = None,
) -> 'Iterator[Line | ObjDefintion]':
    while True:
        if read_uint16be(stream) != 0:
            break

        if number == 0:
            verb = read_uint16be(stream)
            noun1 = read_uint16be(stream)
            noun2 = read_uint16be(stream)
            yield ObjDefintion(verb, noun1, noun2)

        yield Line(list(decode_script(stream, parser, soundmap=soundmap)))


def realize_params(
    params: 'Iterable[str]',
    stream: IO[bytes],
    text_mask: int,
) -> 'Iterator[Param]':
    for ptype in params:
        if ptype == ' ':
            continue
        if ptype == 'T':
            rtypes = {
                0: -1,
                3: -3,
                1: 1,
            }
            num = rtypes[read_uint16be(stream)]
            if num == 1:
                num = read_uint32be(stream)
            yield Param(ptype, num, text_mask)
            continue

        if ptype == 'B':
            num = ord(stream.read(1))
            yield (
                Param(ptype, [ord(stream.read(1))])
                if num == BYTE_MASK
                else Param(ptype, num)
            )
            continue

        if ptype == 'I':
            num = read_uint16be(stream)
            special_items = {
                1: '$1',  # SUBJECT_ITEM
                3: '$2',  # OBJECT_ITEM
                5: '$ME',  # ME_ITEM
                7: '$AC',  # ACTOR_ITEM
                9: '$RM',  # ITEM_A_PARENT
            }
            special = special_items.get(num, None)
            if special is not None:
                yield Param(ptype, special)
            else:
                assert num == 0, num
                num = read_uint32be(stream) + 2
                assert num & WORD_MASK == num, (num & WORD_MASK, num)
                yield Param(ptype, f'<{num}>')
            continue

        if ptype in {
            'v',
            'p',
            'n',
            'a',
            'S',
            'N',
        }:
            num = read_uint16be(stream)
            yield Param(ptype, num)
            continue

        raise NotImplementedError(ptype)


def decode_script(
    stream: IO[bytes],
    parser: 'Parser',
    soundmap: dict[int, set[int]] | None = None,
) -> 'Iterator[Command]':
    while True:
        pos = stream.tell()
        opcode = ord(stream.read(1))
        if opcode == BYTE_MASK:
            break
        cmd, params = parser.optable[opcode]
        args = tuple(realize_params(params, stream, parser.text_mask))
        c = Command(opcode, cmd, args)
        npos = stream.tell()
        yield c
        stream.seek(pos)
        assert stream.read(npos - pos) == bytes(c)
        if soundmap is not None and 'S' in params:
            assert 'T' in params, params
            soundmap[int(args[params.index('T')].value) & WORD_MASK].add(
                int(args[params.index('S')].value),
            )


def parse_args(
    cmds: 'Iterator[str]',
    params: 'Iterable[str]',
    text_mask: int,
) -> 'Iterator[Param]':
    for ptype in params:
        if ptype == ' ':
            continue
        if ptype == 'T':
            num = int(next(cmds))
            if num >= BASE_MIN:
                num |= text_mask
            yield Param(ptype, num, text_mask)
            continue

        if ptype == 'B':
            rnum = next(cmds)
            stripped = rnum.strip('[]')
            if stripped != rnum:
                yield Param(ptype, [int(stripped)])
            else:
                yield Param(ptype, int(rnum))
            continue

        if ptype == 'I':
            yield Param(ptype, next(cmds))
            continue

        if ptype in {
            'v',
            'p',
            'n',
            'a',
            'S',
            'N',
        }:
            yield Param(ptype, int(next(cmds)))
            continue


@dataclass
class Parser:
    optable: 'Mapping[int, tuple[str | None, str]]'
    text_mask: int = 0


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
    if command is not None:
        yield (keywords[command], command, params)


class ParseError(ValueError):
    message: str
    command: str
    sargs: Sequence[str]
    line_number: int
    linetab: str
    file: str | None = None
    sidx: str | None = None
    lidx: int | None = None
    block: int | None = None
    stream: TextIO = sys.stderr

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

    def highlight(self, linetab: str) -> str:
        focus = ' '.join([self.command, *self.sargs])
        return linetab.replace(focus, f'-> {focus} <-', 1)

    def show(self, scr_file: str) -> None:
        print('ERROR: Cannot parse scripts file at', file=self.stream)
        print(
            '\n'.join(
                [
                    f'  FILE: {self.file}',
                    f'  SUBROUTINE: {self.sidx}',
                    f'  LINE: {self.lidx}',
                    f'  BLOCK: {self.block}',
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
        sys.exit(1)


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


def parse_cmds(cmds: 'Iterable[str]', parser: 'Parser') -> 'Iterator[Command]':
    for op, command, args in tokenize_cmds(cmds, parser):
        ename, params = parser.optable[op]
        assert command == ename, (command, ename)
        if len(args) != len(params.rstrip(' ')):
            raise ParameterCountMismatchError(command, args, params)
        try:
            parsed = tuple(parse_args(iter(args), params, parser.text_mask))
        except ValueError as exc:
            raise ArgumentParseError(command, args, params, exc) from exc
        yield Command(op, command, parsed)


def parse_lines(
    lidx: int,
    tabs: 'Iterable[str]',
    parser: 'Parser',
) -> 'Iterator[Line | ObjDefintion]':
    line_number = 0
    for bidx, tab in enumerate(tabs, start=1):
        if tab.startswith('DEF: '):
            assert lidx == 0, lidx
            yield ObjDefintion(*(int(x) for x in tab.split()[1:]))
            line_number += tab.count('\n')
            continue
        cmds = ''.join(x.split('//')[0] for x in tab.split('\n')).split()
        try:
            yield Line(list(parse_cmds(cmds, parser)))
        except ParseError as exc:
            exc.line_number = line_number
            exc.block = bidx
            exc.linetab = '==>\t' + tab
            raise
        line_number += tab.count('\n')


def parse_tables(lines: 'Iterable[str]', parser: 'Parser') -> 'Iterator[Table]':
    line_number = 0
    for line in lines:
        rlidx, *tabs = line.split('==> ')
        lidx = int(rlidx.split('==')[0])
        try:
            yield Table(lidx, list(parse_lines(lidx, tabs, parser)))
        except ParseError as exc:
            exc.lidx = lidx
            exc.line_number += line_number + rlidx.count('\n')
            raise
        line_number += line.count('\n')


def parse_props(props: 'Iterable[str]') -> 'Iterator[Property]':
    for prop in props:
        rdtype, *rprops = prop.rstrip('\n').split('\n\t')
        dtype = ItemType[rdtype]
        aprops = dict(x.split(' //')[0].split(maxsplit=1) for x in rprops)
        dprops: Property
        if dtype == ItemType.OBJECT:
            dprops = {
                'ptype': ItemType.OBJECT,
                'name': Param('T', int(aprops.pop('NAME'))),
                'params': {
                    PropertyType[pkey]: int(val) for pkey, val in aprops.items()
                },
            }
            desc = dprops['params'].get(PropertyType.DESCRIPTION)
            if desc is not None:
                dprops['params'][PropertyType.DESCRIPTION] = Param('T', desc)
        elif dtype == ItemType.ROOM:
            exits = []
            for i in range(6):
                exd = aprops[f'EXIT{1+i}']
                ex: Exit | None
                if exd == '-':
                    ex = None
                else:
                    eto, status = exd.split()
                    ex = {'exit_to': int(eto), 'status': DoorState[status]}
                exits.append(ex)
            dprops = {
                'ptype': ItemType.ROOM,
                'table': int(aprops['TABLE']),
                'exits': exits,
            }
        elif dtype == ItemType.INHERIT:
            dprops = {
                'ptype': ItemType.INHERIT,
                'item': int(aprops['ITEM']),
            }
        elif dtype == ItemType.USERFLAG:
            dprops = {
                'ptype': ItemType.USERFLAG,
                'flag1': int(aprops['1']),
                'flag2': int(aprops['2']),
                'flag3': int(aprops['3']),
                'flag4': int(aprops['4']),
            }
        else:
            raise ValueError(dtype)
        yield dprops
