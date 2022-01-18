import io
import struct
from chiper import decrypt, hebrew_char_map
from gamepc import read_gamepc
from stream import read_uint16be, read_uint32be


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


def read_children(stream, ptype, strings):
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

        if flags & 1:
            sub["params"] += [read_text(stream).resolve(strings)]

        for n in range(1, 16):
            if flags & (1 << n) != 0:
                sub["params"] += [read_uint16be(stream)]

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
    


def read_object(stream, strings):
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
    print(item)

    props = read_uint32be(stream)
    while props:
        props = read_uint16be(stream)
        if props != 0:
            prop = read_children(stream, props, strings)
            prop['type'] = props
            item['children'] += [prop]

    return item


def load_tables(stream, strings, ops):
    while True:
        try:
            if read_uint16be(stream) != 0:
                break
        except struct.error:
            break

        number = read_uint16be(stream)
        yield f'== LINE {number }=='
        for line in load_table(stream, number, strings, ops):
            yield f'==> {line}'


def load_table(stream, number, strings, ops):
    while True:
        if read_uint16be(stream) != 0:
            break
        line_num = 0xFFFF

        if number == 0:
            verb = read_uint16be(stream)
            noun1 = read_uint16be(stream)
            noun2 = read_uint16be(stream)
            yield f'{verb:=} {noun1:=} {noun2:=}'

        parts = decode_script(stream, ops, strings)
        inlined = [' '.join(str(p) for p in part) for part in parts]
        yield '\n\t'.join(inlined)


def realize_params(params, stream, strings):
    for ptype in params:
        if ptype == ' ':
            continue
        if ptype == 'T':
            msg = None
            val = read_uint16be(stream)
            if val == 0:
                t = 0xFFFFFFFF
            elif val == 3:
                t = 0xFFFFFFFD
            else:
                t = read_uint32be(stream)
            num = t & 0xFFFF
            if num != 0xFFFF:
                msg = strings.get(num, "MISSING STRING")
            yield f'{num}("{msg}")'
            continue

        if ptype == 'B':
            num = ord(stream.read(1))
            if num == 0xFF:
                yield [ord(stream.read(1))]
            else:
                yield num
            continue

        if ptype == 'I':
            num = read_uint16be(stream)
            if num == 1:
                yield 'SUBJECT_ITEM'
            elif num == 3:
                yield 'OBJECT_ITEM'
            elif num == 5:
                yield 'ME_ITEM'
            elif num == 7:
                yield 'ACTOR_ITEM'
            elif num == 9:
                yield 'ITEM_A_PARENT'
            else:
                num = read_uint32be(stream) + 2 & 0xFFFF
                yield f'<{num}>'
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
            yield num
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


def decode_script(stream, ops, strings):
    while True:
        opcode = ord(stream.read(1))
        if opcode == 0xFF:
            break
        # print('DEBUG', opcode, ops[opcode], simon_ops[opcode])
        cmd, params = ops[opcode]
        if params == 'x':
            args = ()
            yield cmd, *args
            break
        args = tuple(realize_params(params, stream, strings))
        # print(cmd, *args)
        cmd = f'({hex(opcode)}) {cmd}'
        yield cmd, *args

if __name__ == '__main__':

    with open('GAMEPC', 'rb') as f:
        read_gamepc_script(f)
