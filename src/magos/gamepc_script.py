from dataclasses import dataclass
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


KEY_ROOM = 1
KEY_OBJECT = 2
KEY_PLAYER = 3
KEY_SUPER_ROOM = 4
KEY_CHAIN = 8
KEY_USERFLAG = 9


object_keys = {0: 'description', 4: 'icon', 8: 'number', 9: 'voice'}


def read_properties(stream, ptype, soundmap=None):
    if ptype == KEY_ROOM:
        sub = {"exits": []}
        fr1 = read_uint16be(stream)
        fr2 = read_uint16be(stream)

        # j = fr2
        # size = 10
        # for i in range(6):
        #     if j & 3:
        #         size += 2
        #     j >>= 2

        sub['table'] = fr1
        sub['exit_states'] = fr2

        j = fr2
        for i in range(6):
            if j & 3:
                sub['exits'] += [read_item(stream)]
            j >>= 2

        return sub

    elif ptype == KEY_OBJECT:

        sub = {'params': {}}

        flags = read_uint32be(stream)

        # size = 10
        # for n in range(16):
        #     if flags & (1 << n) != 0:
        #         size += 2

        text = None
        if flags & 1:
            text = Param('T', read_uint32be(stream))
            sub['params'][object_keys[0]] = text

        for n in range(1, 16):
            if flags & (1 << n) != 0:
                sub['params'][object_keys[n]] = read_uint16be(stream)

        if soundmap is not None and text is not None:
            voice = sub['params'].get('voice')
            if voice is not None:
                soundmap[text.value].add(voice)
        sub['name'] = Param('T', read_uint32be(stream))

        return sub

    elif ptype == KEY_PLAYER:
        raise NotImplementedError('KEY_PLAYER')
    elif ptype == KEY_SUPER_ROOM:
        raise NotImplementedError('KEY_SUPER_ROOM')
    elif ptype == KEY_CHAIN:
        raise NotImplementedError('KEY_CHAIN')
    elif ptype == KEY_USERFLAG:
        raise NotImplementedError('KEY_USERFLAG')
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
            prop['type'] = {1: 'ROOM', 2: 'OBJECT'}[props]
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
            output += write_uint16be({'ROOM': 1, 'OBJECT': 2}[prop['type']])
            if prop['type'] == 'ROOM':
                output += write_uint16be(prop['table'])
                exit_states = 0
                sout = bytearray()
                for exit in prop['exits']:
                    assert False
                output += write_uint16be(exit_states) + bytes(sout)

            elif prop['type'] == 'OBJECT':
                sout = bytearray()
                flags = 0
                for pow, key in object_keys.items():
                    val = prop['params'].pop(key, None)
                    if val is not None:
                        flags |= 2**pow
                        sout += (
                            write_uint32be(val.value)
                            if pow == 0
                            else write_uint16be(val)
                        )
                assert not prop['params'], prop['params']
                output += write_uint32be(flags) + bytes(sout)
                output += write_uint32be(prop['name'].value)
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
        aprops = dict(x.split(' //')[0].split() for x in rprops)
        if dtype == 'OBJECT':
            dprops = {
                'name': Param('T', int(aprops.pop('NAME'))),
                'params': {pkey.lower(): int(val) for pkey, val in aprops.items()},
            }
            desc = dprops['params'].get('description')
            if desc is not None:
                dprops['params']['description'] = Param('T', desc)
        elif dtype == 'ROOM':
            exits = aprops['EXITS']
            dprops = {
                'table': int(aprops['TABLE']),
                'exit_states': int(aprops['EXIT_STATE']),
                'exits': [int(x) for x in exits.split('|')] if exits != '-' else [],
            }
        yield {'type': dtype, **dprops}
