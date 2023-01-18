from dataclasses import dataclass
import struct
from typing import Any, Iterator, Sequence

from magos.stream import read_uint16be, read_uint32be


def read_item(stream):
    val = read_uint32be(stream)
    return 0 if val == 0xFFFFFFFF else val + 2


KEY_ROOM = 1
KEY_OBJECT = 2
KEY_PLAYER = 3
KEY_SUPER_ROOM = 4
KEY_CHAIN = 8
KEY_USERFLAG = 9


class Text:
    def __init__(self, num) -> None:
        self._num = num

    def resolve(self, table) -> str:
        return table[self._num]


def read_text(stream):
    return Text(read_uint32be(stream))


def read_children(stream, ptype, strings, soundmap=None):
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

        sub = {"params": []}

        flags = read_uint32be(stream)

        # size = 10
        # for n in range(16):
        #     if flags & (1 << n) != 0:
        #         size += 2

        sub['flags'] = flags

        text = None
        if flags & 1:
            text = read_text(stream)
            sub["params"] += [text.resolve(strings)]

        for n in range(1, 16):
            if flags & (1 << n) != 0:
                sub["params"] += [read_uint16be(stream)]

        if soundmap is not None and text is not None:
            soundmap[text._num].add(sub['params'][-1])
        sub['name'] = read_text(stream).resolve(strings)

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


def read_objects(stream, item_count, strings, soundmap=None):
    null = {'children': []}
    player = {'children': []}
    return [null, player] + [
        read_object(stream, strings, soundmap=soundmap)
        for i in range(2, item_count)
    ]


def read_object(stream, strings, soundmap=None):
    item = {}
    item['adjective'] = read_uint16be(stream)
    item['noun'] = read_uint16be(stream)
    item['state'] = read_uint16be(stream)
    item['next'] = read_item(stream)
    item['child'] = read_item(stream)
    item['parent'] = read_item(stream)
    item['unk'] = read_uint16be(stream)
    item['class'] = read_uint16be(stream)
    item['children'] = []
    # print(item)

    props = read_uint32be(stream)
    while props:
        props = read_uint16be(stream)
        if props != 0:
            prop = read_children(stream, props, strings, soundmap=soundmap)
            prop['type'] = props
            item['children'] += [prop]

    return item


@dataclass
class Param:
    ptype: str
    value: Any

    def __str__(self) -> str:
        if self.ptype == 'T' and self.value > 0:
            # either value is < 0x8000 or it masked with 0xFFFF0000, never both
            assert bool(self.value < 0x8000) != bool(self.value & 0xFFFF0000), self.value
            return str(self.value & 0xFFFF)
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


def load_tables(stream, ops, soundmap=None):
    while True:
        try:
            if read_uint16be(stream) != 0:
                break
        except struct.error:
            break

        number = read_uint16be(stream)
        yield Table(number, list(load_table(stream, number, ops, soundmap=soundmap)))


def load_table(stream, number, ops, soundmap=None):
    while True:
        if read_uint16be(stream) != 0:
            break

        if number == 0:
            verb = read_uint16be(stream)
            noun1 = read_uint16be(stream)
            noun2 = read_uint16be(stream)
            yield ObjDefintion(verb, noun1, noun2)

        yield Line(list(decode_script(stream, ops, soundmap=soundmap)))


def realize_params(params, stream):
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
            yield Param(ptype, num)
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


def decode_script(stream, ops, soundmap=None):
    while True:
        pos = stream.tell()
        opcode = ord(stream.read(1))
        if opcode == 0xFF:
            break
        # print('DEBUG', opcode, ops[opcode], simon_ops[opcode])
        cmd, params = ops[opcode]
        args = tuple(realize_params(params, stream))
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


def parse_args(cmds, params):
    for ptype in params:
        if ptype == ' ':
            continue
        if ptype == 'T':
            num = int(next(cmds))
            if num >= 0x8000:
                num |= 0xFFFF0000
            yield Param(ptype, num)
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


def parse_cmds(cmds, optable):
    # print(cmds)
    cmds = iter(cmds)
    while True:
        op = next(cmds, None)
        if not op:
            break
        num = int(op.strip('()'), 16)
        ename, params = optable[num]
        cname = next(cmds)
        assert cname == ename, (cname, ename)

        yield Command(num, cname, tuple(parse_args(cmds, params)))


def parse_lines(lidx, tabs, optable):
    for tab in tabs:
        if tab.startswith('DEF: '):
            assert lidx == 0, lidx
            yield ObjDefintion(*(int(x) for x in tab.split()[1:]))
            continue
        cmds = ''.join(x.split('//')[0] for x in tab.split('\n')).split()
        yield Line(list(parse_cmds(cmds, optable)))


def parse_tables(lines, optable):
    for line in lines:
        lidx, *tabs = line.split('==> ')
        lidx = int(lidx.split('==')[0])
        yield Table(lidx, list(parse_lines(lidx, tabs, optable)))
