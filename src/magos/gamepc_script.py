from dataclasses import dataclass
from enum import IntEnum
import struct
from typing import Any, Iterator, Mapping, Sequence

from magos.stream import (
    read_uint16be,
    read_uint32be,
    write_uint16be,
    write_uint32be,
)


def read_item(stream):
    val = read_uint32be(stream)
    return 0 if val == 0xFFFFFFFF else val + 2


def write_item(num):
    return write_uint32be(0xFFFFFFFF if num == 0 else num - 2)


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


def read_properties(stream, ptype, soundmap=None):
    if ptype == ItemType.ROOM:
        sub = {"exits": []}
        table = read_uint16be(stream)
        exit_states = read_uint16be(stream)

        sub['table'] = table

        for _ in range(6):
            ex = None
            if exit_states & 3 != 0:
                ex = {
                    'exit_to': read_item(stream),
                    'status': DoorState(exit_states & 3),
                }
                assert ex['exit_to'] != 0
            sub['exits'].append(ex)
            exit_states >>= 2

        return sub

    elif ptype == ItemType.OBJECT:

        sub = {'params': {}}

        flags = read_uint32be(stream)

        # size = 10
        # for n in range(16):
        #     if flags & (1 << n) != 0:
        #         size += 2

        text = None
        if flags & 1:
            text = Param('T', read_uint32be(stream))
            sub['params'][PropertyType(0)] = text

        for n in range(1, 16):
            if flags & (1 << n) != 0:
                sub['params'][PropertyType(n)] = read_uint16be(stream)

        flags >>= 16
        if flags:
            sub['params'][PropertyType.FLAGS] = flags

        if soundmap is not None and text is not None:
            voice = sub['params'].get('voice')
            if voice is not None:
                soundmap[text.value].add(voice)
        sub['name'] = Param('T', read_uint32be(stream))

        return sub

    elif ptype == ItemType.PLAYER:
        raise NotImplementedError('KEY_PLAYER')
    elif ptype == ItemType.SUPER_ROOM:
        raise NotImplementedError('KEY_SUPER_ROOM')
    elif ptype == ItemType.CHAIN:
        raise NotImplementedError('KEY_CHAIN')
    elif ptype == ItemType.USERFLAG:
        return {
            '1': read_uint16be(stream),
            '2': read_uint16be(stream),
            '3': read_uint16be(stream),
            '4': read_uint16be(stream),
        }
    elif ptype == ItemType.INHERIT:
        return {'item': read_item(stream)}
    else:
        raise NotImplementedError(ptype)


def read_objects(stream, item_count, soundmap=None):
    null = {'children': []}
    player = {'children': []}
    return [null, player] + [
        read_object(stream, soundmap=soundmap) for i in range(2, item_count)
    ]


def read_object(stream, soundmap=None):
    item = {}
    item['adjective'] = read_uint16be(stream)
    item['noun'] = read_uint16be(stream)
    item['state'] = read_uint16be(stream)
    item['next'] = read_item(stream)
    item['child'] = read_item(stream)
    item['parent'] = read_item(stream)
    item['unk'] = read_uint16be(stream)
    item['class'] = read_uint16be(stream)
    item['properties'] = []
    # print(item)

    props = read_uint32be(stream)
    item['properties_init'] = props
    while props:
        props = read_uint16be(stream)
        if props != 0:
            prop = read_properties(stream, props, soundmap=soundmap)
            prop['type'] = ItemType(props)
            item['properties'] += [prop]

    return item


def write_objects_bytes(objects):
    output = bytearray()
    for obj in objects:
        output += write_uint16be(obj['adjective'])
        output += write_uint16be(obj['noun'])
        output += write_uint16be(obj['state'])
        output += write_item(obj['next'])
        output += write_item(obj['child'])
        output += write_item(obj['parent'])
        output += write_uint16be(obj['unk'])
        output += write_uint16be(obj['class'])
        output += write_uint32be(obj['properties_init'])
        for prop in obj['properties']:
            output += write_uint16be(prop['type'])
            if prop['type'] == ItemType.ROOM:
                output += write_uint16be(prop['table'])
                exit_states = 0
                sout = bytearray()
                for ex in prop['exits'][::-1]:
                    exit_states <<= 2
                    if ex is not None:
                        assert ex['status'] != 0, ex
                        sout = write_item(ex['exit_to']) + sout
                        exit_states |= ex['status']
                output += write_uint16be(exit_states) + bytes(sout)

            elif prop['type'] == ItemType.OBJECT:
                sout = bytearray()
                flags = prop['params'].pop(PropertyType.FLAGS, 0) << 16
                for key in PropertyType:
                    val = prop['params'].pop(key, None)
                    if val is not None:
                        flags |= 2**key
                        sout += (
                            write_uint32be(val.value)
                            if key == 0
                            else write_uint16be(val)
                        )
                assert not prop['params'], prop['params']
                output += write_uint32be(flags) + bytes(sout)
                output += write_uint32be(prop['name'].value)
            elif prop['type'] == ItemType.INHERIT:
                output += write_item(prop['item'])
            elif prop['type'] == ItemType.USERFLAG:
                output += (
                    write_uint16be(prop['1'])
                    + write_uint16be(prop['2'])
                    + write_uint16be(prop['3'])
                    + write_uint16be(prop['4'])
                )
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

    def resolve(self, all_strings) -> str:
        if self.ptype == 'T':
            msg = None
            num = self.value & 0xFFFF
            if num != 0xFFFF:
                msg = all_strings.get(self.value & 0xFFFF, "MISSING STRING")
            return f'{{{msg}}}'
        return ''

    def __bytes__(self):
        if self.ptype == 'T':
            if self.value == -1:
                return (0).to_bytes(2, byteorder='big', signed=False)
            if self.value == -3:
                return (3).to_bytes(2, byteorder='big', signed=False)
            else:
                return (1).to_bytes(
                    2, byteorder='big', signed=False
                ) + self.value.to_bytes(4, byteorder='big', signed=False)

        if self.ptype == 'B':
            if isinstance(self.value, list):
                return bytes([0xFF] + self.value)
            return bytes([self.value])

        if self.ptype == 'I':
            if self.value == '$1':
                return (1).to_bytes(2, byteorder='big', signed=False)
            if self.value == '$2':
                return (3).to_bytes(2, byteorder='big', signed=False)
            if self.value == '$ME':
                return (5).to_bytes(2, byteorder='big', signed=False)
            if self.value == '$AC':
                return (7).to_bytes(2, byteorder='big', signed=False)
            if self.value == '$RM':
                return (9).to_bytes(2, byteorder='big', signed=False)
            num = int(self.value[1:-1]) - 2
            return (0).to_bytes(2, byteorder='big', signed=False) + num.to_bytes(
                4, byteorder='big', signed=False
            )

        if self.ptype in {
            'v',
            'p',
            'n',
            'a',
            'S',
            'N',
        }:
            return self.value.to_bytes(2, byteorder='big', signed=False)


@dataclass
class Command:
    opcode: int
    cmd: str
    args: Sequence[Param]

    def __str__(self) -> str:
        cmd = f'(0x{self.opcode:02x}) {self.cmd}'
        return ' '.join(str(x) for x in (cmd, *self.args))

    def resolve(self, all_strings) -> Iterator[str]:
        cmd = f'(0x{self.opcode:02x}) {self.cmd}'
        comments = ''.join(x.resolve(all_strings) for x in self.args)
        if comments:
            comments = ' // ' + f'{comments}'
        return ' '.join(str(x) for x in (cmd, *self.args)) + comments

    def __bytes__(self):
        return bytes([self.opcode]) + b''.join(bytes(p) for p in self.args)


@dataclass
class Line:
    parts: Sequence[Command]

    def __str__(self) -> str:
        inlined = [str(part) for part in self.parts]
        joined = '\n\t'.join(inlined)
        return f'==> {joined}'

    def resolve(self, all_strings):
        inlined = [part.resolve(all_strings) for part in self.parts]
        joined = '\n\t'.join(inlined)
        return f'==> {joined}'

    def __bytes__(self):
        return b''.join(bytes(cmd) for cmd in self.parts) + b'\xFF'


@dataclass
class Table:
    number: int
    parts: Sequence[Line]

    def resolve(self, all_strings) -> Iterator[str]:
        yield f'== LINE {self.number}=='
        yield from (part.resolve(all_strings) for part in self.parts)

    def __bytes__(self):
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

    def resolve(self, all_strings) -> Iterator[str]:
        return f'==> DEF: {self.verb:=} {self.noun1:=} {self.noun2:=}'

    def __bytes__(self):
        return (
            self.verb.to_bytes(2, byteorder='big', signed=False)
            + self.noun1.to_bytes(2, byteorder='big', signed=False)
            + self.noun2.to_bytes(2, byteorder='big', signed=False)
        )


def load_tables(stream, parser, soundmap=None):
    while True:
        try:
            if read_uint16be(stream) != 0:
                break
        except struct.error:
            break

        number = read_uint16be(stream)
        yield Table(number, list(load_table(stream, number, parser, soundmap=soundmap)))


def load_table(stream, number, parser, soundmap=None):
    while True:
        if read_uint16be(stream) != 0:
            break

        if number == 0:
            verb = read_uint16be(stream)
            noun1 = read_uint16be(stream)
            noun2 = read_uint16be(stream)
            yield ObjDefintion(verb, noun1, noun2)

        yield Line(list(decode_script(stream, parser, soundmap=soundmap)))


def realize_params(params, stream, text_mask):
    for ptype in params:
        if ptype == ' ':
            continue
        if ptype == 'T':
            val = read_uint16be(stream)
            if val == 0:
                num = -1
            elif val == 3:
                num = -3
            else:
                assert val == 1, val
                num = read_uint32be(stream)
            yield Param(ptype, num, text_mask)
            continue

        if ptype == 'B':
            num = ord(stream.read(1))
            if num == 0xFF:
                yield Param(ptype, [ord(stream.read(1))])
            else:
                yield Param(ptype, num)
            continue

        if ptype == 'I':
            num = read_uint16be(stream)
            if num == 1:
                yield Param(ptype, '$1')  # SUBJECT_ITEM
            elif num == 3:
                yield Param(ptype, '$2')  # OBJECT_ITEM
            elif num == 5:
                yield Param(ptype, '$ME')  # ME_ITEM
            elif num == 7:
                yield Param(ptype, '$AC')  # 'ACTOR_ITEM
            elif num == 9:
                yield Param(ptype, '$RM')  # ITEM_A_PARENT
            else:
                assert num == 0, num
                num = read_uint32be(stream) + 2
                assert num & 0xFFFF == num, (num & 0xFFFF, num)
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

        # if ptype == 'J':
        #     yield '->'
        #     continue

        # if ptype == 'W':
        #     num = read_uint16be(stream)
        #     yield [num - 3000] if 30000 <= num < 30512 else num
        #     continue

        # if ptype == 'V':
        #     num = ord(stream.read(1))
        #     if num == 0xFF:
        #         yield [[ord(stream.read(1))]]
        #     else:
        #         yield [num]
        #     continue

        raise NotImplementedError(ptype)


def decode_script(stream, parser, soundmap=None):
    while True:
        pos = stream.tell()
        opcode = ord(stream.read(1))
        if opcode == 0xFF:
            break
        # print('DEBUG', opcode, ops[opcode], simon_ops[opcode])
        cmd, params = parser.optable[opcode]
        args = tuple(realize_params(params, stream, parser.text_mask))
        if cmd is None:
            print(f'WARNING: unknown condname for opcode {hex(opcode)}')
        c = Command(opcode, cmd, args)
        npos = stream.tell()
        yield c
        stream.seek(pos)
        assert stream.read(npos - pos) == bytes(c)
        if soundmap is not None and 'S' in params:
            assert 'T' in params, params
            soundmap[int(args[params.index('T')].value)].add(
                int(args[params.index('S')].value)
            )


def parse_args(cmds, params, text_mask):
    for ptype in params:
        if ptype == ' ':
            continue
        if ptype == 'T':
            num = int(next(cmds))
            if num >= 0x8000:
                num |= text_mask
            yield Param(ptype, num, text_mask)
            continue

        if ptype == 'B':
            num = next(cmds)
            stripped = num.strip('[]')
            if stripped != num:
                yield Param(ptype, [int(stripped)])
            else:
                yield Param(ptype, int(num))
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
    optable: Mapping[int, str]
    text_mask: int = 0


def parse_cmds(cmds, parser):
    # print(cmds)
    cmds = iter(cmds)
    while True:
        op = next(cmds, None)
        if not op:
            break
        num = int(op.strip('()'), 16)
        ename, params = parser.optable[num]
        cname = next(cmds)
        assert cname == ename, (cname, ename)

        yield Command(num, cname, tuple(parse_args(cmds, params, parser.text_mask)))


def parse_lines(lidx, tabs, parser):
    for tab in tabs:
        if tab.startswith('DEF: '):
            assert lidx == 0, lidx
            yield ObjDefintion(*(int(x) for x in tab.split()[1:]))
            continue
        cmds = ''.join(x.split('//')[0] for x in tab.split('\n')).split()
        yield Line(list(parse_cmds(cmds, parser)))


def parse_tables(lines, parser):
    for line in lines:
        lidx, *tabs = line.split('==> ')
        lidx = int(lidx.split('==')[0])
        yield Table(lidx, list(parse_lines(lidx, tabs, parser)))


def parse_props(props):
    for prop in props:
        dtype, *rprops = prop.rstrip('\n').split('\n\t')
        dtype = ItemType[dtype]
        aprops = dict(x.split(' //')[0].split(maxsplit=1) for x in rprops)
        if dtype == ItemType.OBJECT:
            dprops = {
                'name': Param('T', int(aprops.pop('NAME'))),
                'params': {PropertyType[pkey]: int(val) for pkey, val in aprops.items()},
            }
            desc = dprops['params'].get(PropertyType.DESCRIPTION)
            if desc is not None:
                dprops['params'][PropertyType.DESCRIPTION] = Param('T', desc)
        elif dtype == ItemType.ROOM:
            exits = []
            for i in range(6):
                exd = aprops[f'EXIT{1+i}']
                if exd == '-':
                    ex = None
                else:
                    eto, status = exd.split()
                    ex = {'exit_to': int(eto), 'status': DoorState[status]}
                exits.append(ex)
            dprops = {
                'table': int(aprops['TABLE']),
                'exits': exits,
            }
        elif dtype == ItemType.INHERIT:
            dprops = {
                'item': int(aprops['ITEM']),
            }
        elif dtype == ItemType.USERFLAG:
            dprops = {
                '1': int(aprops['1']),
                '2': int(aprops['2']),
                '3': int(aprops['3']),
                '4': int(aprops['4']),
            }
        else:
            raise ValueError(dtype)
        yield {'type': dtype, **dprops}
