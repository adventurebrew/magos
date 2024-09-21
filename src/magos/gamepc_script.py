import io
import struct
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
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

from magos.detection import GameID
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

CMD_EOL = 10000

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
    GENEXIT = 4
    SUPER_ROOM = 4
    CONTAINER = 7
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
    UNK10 = 10  # Used in Elvira 2
    UNK11 = 11  # Used in Elvira 2

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
    name: 'Param | None'


def read_object_property(
    stream: IO[bytes],
    game: 'GameID',
    soundmap: dict[int, set[int]] | None = None,
) -> ObjectProperty:
    params: dict[PropertyType, int | Param] = {}

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
    name = None
    if game != GameID.elvira2:
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


class ContainerProperty(TypedDict):
    ptype: Literal[ItemType.CONTAINER]
    volume: int
    flags: int


class SuperRoomProperty(TypedDict):
    ptype: Literal[ItemType.SUPER_ROOM]
    srid: int
    x: int
    y: int
    z: int
    exits: Sequence[int]


class ElviraUserFlagProperty(UserFlagProperty):
    game: Literal[GameID.elvira1]
    flag5: int
    flag6: int
    flag7: int
    flag8: int
    item1: int
    item2: int
    item3: int
    item4: int


class ElviraObjectProperty(TypedDict):
    ptype: Literal[ItemType.OBJECT]
    game: Literal[GameID.elvira1]
    text1: 'Param'
    text2: 'Param'
    text3: 'Param'
    text4: 'Param'
    size: int
    weight: int
    flags: int


class ElviraEoomProperty(TypedDict):
    ptype: Literal[ItemType.ROOM]
    game: Literal[GameID.elvira1]
    short: 'Param'
    long: 'Param'
    flags: int


class GenExitProperty(TypedDict):
    ptype: Literal[ItemType.GENEXIT]
    game: Literal[GameID.elvira1]
    dest1: int
    dest2: int
    dest3: int
    dest4: int
    dest5: int
    dest6: int
    dest7: int
    dest8: int
    dest9: int
    dest10: int
    dest11: int
    dest12: int


class ChainProperty(TypedDict):
    ptype: Literal[ItemType.CHAIN]
    item: int


Property = (
    RoomProperty
    | ObjectProperty
    | UserFlagProperty
    | InheritProperty
    | ContainerProperty
    | SuperRoomProperty
    | ElviraUserFlagProperty
    | ElviraObjectProperty
    | ElviraEoomProperty
    | GenExitProperty
    | ChainProperty
)


class Item(TypedDict):
    adjective: int
    noun: int
    state: int
    next_item: int
    child: int
    parent: int
    actor_table: int
    item_class: int
    properties_init: int
    properties: Sequence[Property]
    name: 'Param | None'


class ElviraItem(Item):
    perception: int
    action_table: int
    users: int


def read_properties_old(
    stream: IO[bytes],
    ptype: ItemType,
    game: 'GameID',
    soundmap: dict[int, set[int]] | None = None,
) -> Property:
    prop: Property
    if ptype == ItemType.INHERIT:
        prop = InheritProperty(
            ptype=ItemType.INHERIT,
            item=read_item(stream),
        )
    elif ptype == ItemType.CONTAINER:
        prop = ContainerProperty(
            ptype=ItemType.CONTAINER,
            volume=read_uint16be(stream),
            flags=read_uint16be(stream),
        )
    elif ptype == ItemType.USERFLAG:
        prop = ElviraUserFlagProperty(
            ptype=ItemType.USERFLAG,
            game=GameID.elvira1,
            flag1=read_uint16be(stream),
            flag2=read_uint16be(stream),
            flag3=read_uint16be(stream),
            flag4=read_uint16be(stream),
            flag5=read_uint16be(stream),
            flag6=read_uint16be(stream),
            flag7=read_uint16be(stream),
            flag8=read_uint16be(stream),
            item1=read_item(stream),
            item2=read_item(stream),
            item3=read_item(stream),
            item4=read_item(stream),
        )
    elif ptype == ItemType.OBJECT:
        prop = ElviraObjectProperty(
            ptype=ItemType.OBJECT,
            game=GameID.elvira1,
            text1=Param('T', read_uint32be(stream)),
            text2=Param('T', read_uint32be(stream)),
            text3=Param('T', read_uint32be(stream)),
            text4=Param('T', read_uint32be(stream)),
            size=read_uint16be(stream),
            weight=read_uint16be(stream),
            flags=read_uint16be(stream),
        )
    elif ptype == ItemType.ROOM:
        prop = ElviraEoomProperty(
            ptype=ItemType.ROOM,
            game=GameID.elvira1,
            short=Param('T', read_uint32be(stream)),
            long=Param('T', read_uint32be(stream)),
            flags=read_uint16be(stream),
        )
    elif ptype == ItemType.GENEXIT:
        prop = GenExitProperty(
            ptype=ItemType.GENEXIT,
            game=GameID.elvira1,
            dest1=read_item(stream),
            dest2=read_item(stream),
            dest3=read_item(stream),
            dest4=read_item(stream),
            dest5=read_item(stream),
            dest6=read_item(stream),
            dest7=read_item(stream),
            dest8=read_item(stream),
            dest9=read_item(stream),
            dest10=read_item(stream),
            dest11=read_item(stream),
            dest12=read_item(stream),
        )
    elif ptype == ItemType.CHAIN:
        prop = ChainProperty(
            ptype=ItemType.CHAIN,
            item=read_item(stream),
        )
    else:
        raise NotImplementedError(ptype)
    return prop


def read_properties(
    stream: IO[bytes],
    ptype: ItemType,
    game: 'GameID',
    soundmap: dict[int, set[int]] | None = None,
) -> Property:
    if ptype == ItemType.ROOM:
        return read_room(stream)
    if ptype == ItemType.OBJECT:
        return read_object_property(stream, game, soundmap=soundmap)
    if ptype == ItemType.PLAYER:
        raise NotImplementedError('KEY_PLAYER')
    if ptype == ItemType.SUPER_ROOM:
        srid = read_uint16be(stream)
        x = read_uint16be(stream)
        y = read_uint16be(stream)
        z = read_uint16be(stream)
        return SuperRoomProperty(
            ptype=ItemType.SUPER_ROOM,
            srid=srid,
            x=x,
            y=y,
            z=z,
            exits=[read_uint16be(stream) for _ in range(x * y * z)],
        )
    if ptype == ItemType.CONTAINER:
        raise NotImplementedError('CONTAINER')
        return ContainerProperty(
            ptype=ItemType.CONTAINER,
            volume=read_uint16be(stream),
            flags=read_uint16be(stream),
        )
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
    game: 'GameID',
    soundmap: dict[int, set[int]] | None = None,
) -> Sequence[Item]:
    return [
        read_object(stream, game=game, soundmap=soundmap) for _ in range(2, item_count)
    ]


def read_object(
    stream: IO[bytes],
    game: 'GameID',
    soundmap: dict[int, set[int]] | None = None,
) -> Item:
    item_name = None
    if game <= GameID.elvira2:
        item_name = Param('T', read_uint32be(stream))
    adjective = read_uint16be(stream)
    noun = read_uint16be(stream)
    state = read_uint16be(stream)
    if game == GameID.elvira1:
        perception = read_uint16be(stream)
    next_item = read_item(stream)
    child = read_item(stream)
    parent = read_item(stream)
    actor_table = read_uint16be(stream)
    if game == GameID.elvira1:
        action_table = read_uint16be(stream)
        users = read_uint16be(stream)
    item_class = read_uint16be(stream)
    properties_init = read_uint32be(stream)
    properties = []
    props = properties_init
    while props:
        props = read_uint16be(stream)
        if props != 0:
            ptype = ItemType(props)
            read = read_properties_old if game == GameID.elvira1 else read_properties
            properties.append(read(stream, ptype, game, soundmap=soundmap))
    it = Item(
        adjective=adjective,
        noun=noun,
        state=state,
        next_item=next_item,
        child=child,
        parent=parent,
        actor_table=actor_table,
        item_class=item_class,
        properties_init=properties_init,
        properties=properties,
        name=item_name,
    )
    if game == GameID.elvira1:
        return ElviraItem(
            **it,
            perception=perception,
            action_table=action_table,
            users=users,
        )
    return it


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
    params = dict(prop['params'])
    sout = bytearray()
    flags = cast(int, params.pop(PropertyType.FLAGS, 0)) << 16
    for key in PropertyType:
        val = params.pop(key, None)
        if val is not None:
            flags |= 2**key
            sout += (
                write_uint32be(cast(Param, val).value)
                if key == 0
                else write_uint16be(cast(int, val))
            )
    assert not params, params
    if prop['name']:
        sout += write_uint32be(prop['name'].value)
    return write_uint32be(flags) + bytes(sout)


def write_user_flag(prop: UserFlagProperty) -> bytes:
    return (
        write_uint16be(prop['flag1'])
        + write_uint16be(prop['flag2'])
        + write_uint16be(prop['flag3'])
        + write_uint16be(prop['flag4'])
    )


def add_mux_room_property(
    prop: RoomProperty | ElviraEoomProperty,
    output: bytearray,
) -> None:
    if prop.get('game') == GameID.elvira1:
        prop = cast(ElviraEoomProperty, prop)
        output += write_uint32be(prop['short'].value)
        output += write_uint32be(prop['long'].value)
        output += write_uint16be(prop['flags'])
    else:
        prop = cast(RoomProperty, prop)
        output += write_room(prop)


def write_object_property_elvira(prop: ElviraObjectProperty) -> bytes:
    return (
        write_uint32be(prop['text1'].value)
        + write_uint32be(prop['text2'].value)
        + write_uint32be(prop['text3'].value)
        + write_uint32be(prop['text4'].value)
        + write_uint16be(prop['size'])
        + write_uint16be(prop['weight'])
        + write_uint16be(prop['flags'])
    )


def add_mux_object_property(
    prop: ObjectProperty | ElviraObjectProperty,
    output: bytearray,
) -> None:
    if prop.get('game') == GameID.elvira1:
        prop = cast(ElviraObjectProperty, prop)
        output += write_object_property_elvira(prop)
    else:
        prop = cast(ObjectProperty, prop)
        output += write_object_property(prop)


def add_mux_user_flag(
    prop: UserFlagProperty | ElviraUserFlagProperty,
    output: bytearray,
) -> None:
    if prop.get('game') == GameID.elvira1:
        prop = cast(ElviraUserFlagProperty, prop)
        output += write_uint16be(prop['flag1'])
        output += write_uint16be(prop['flag2'])
        output += write_uint16be(prop['flag3'])
        output += write_uint16be(prop['flag4'])
        output += write_uint16be(prop['flag5'])
        output += write_uint16be(prop['flag6'])
        output += write_uint16be(prop['flag7'])
        output += write_uint16be(prop['flag8'])
        output += write_item(prop['item1'])
        output += write_item(prop['item2'])
        output += write_item(prop['item3'])
        output += write_item(prop['item4'])
    else:
        output += write_user_flag(prop)


def add_mux_super_room_genexit(
    prop: SuperRoomProperty | GenExitProperty,
    output: bytearray,
) -> None:
    if prop.get('game') == GameID.elvira1:
        prop = cast(GenExitProperty, prop)
        output += write_item(prop['dest1'])
        output += write_item(prop['dest2'])
        output += write_item(prop['dest3'])
        output += write_item(prop['dest4'])
        output += write_item(prop['dest5'])
        output += write_item(prop['dest6'])
        output += write_item(prop['dest7'])
        output += write_item(prop['dest8'])
        output += write_item(prop['dest9'])
        output += write_item(prop['dest10'])
        output += write_item(prop['dest11'])
        output += write_item(prop['dest12'])
    else:
        prop = cast(SuperRoomProperty, prop)
        output += write_uint16be(prop['srid'])
        output += write_uint16be(prop['x'])
        output += write_uint16be(prop['y'])
        output += write_uint16be(prop['z'])
        for ex in prop['exits']:
            output += write_uint16be(ex)


def write_property_bytes(prop: Property, output: bytearray) -> None:
    output += write_uint16be(prop['ptype'])
    if prop['ptype'] == ItemType.ROOM:
        add_mux_room_property(prop, output)
    elif prop['ptype'] == ItemType.OBJECT:
        add_mux_object_property(prop, output)
    elif prop['ptype'] == ItemType.INHERIT:
        output += write_item(prop['item'])
    elif prop['ptype'] == ItemType.USERFLAG:
        add_mux_user_flag(prop, output)
    elif prop['ptype'] == ItemType.CONTAINER:
        output += write_uint16be(prop['volume'])
        output += write_uint16be(prop['flags'])
    elif prop['ptype'] == ItemType.CHAIN:
        output += write_item(prop['item'])
    elif prop['ptype'] in {ItemType.SUPER_ROOM, ItemType.GENEXIT}:
        add_mux_super_room_genexit(prop, output)
    else:
        raise ValueError(prop)


def write_objects_bytes(
    objects: 'Sequence[Item]',
    game: 'GameID',
) -> bytes:
    output = bytearray()
    for obj in objects:
        if game <= GameID.elvira2:
            assert obj['name'] is not None, obj
            output += write_uint32be(obj['name'].value)
        else:
            assert obj.get('name') is None, obj
            obj['name'] = None
        output += write_uint16be(obj['adjective'])
        output += write_uint16be(obj['noun'])
        output += write_uint16be(obj['state'])
        if game == GameID.elvira1:
            obj = cast(ElviraItem, obj)
            output += write_uint16be(obj['perception'])
        output += write_item(obj['next_item'])
        output += write_item(obj['child'])
        output += write_item(obj['parent'])
        output += write_uint16be(obj['actor_table'])
        if game == GameID.elvira1:
            obj = cast(ElviraItem, obj)
            output += write_uint16be(obj['action_table'])
            output += write_uint16be(obj['users'])
        output += write_uint16be(obj['item_class'])
        output += write_uint32be(obj['properties_init'])
        for prop in obj['properties']:
            write_property_bytes(prop, output)
        if obj['properties']:
            output += write_uint16be(0)

    # Verify encoded objects can be decoded back
    with io.BytesIO(output) as f:
        for obj in objects:
            encoded = read_object(f, game)
            assert obj == encoded, (obj, encoded)
        rest = f.read()
        assert not rest, rest

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


@dataclass
class ParamElvira(Param):
    def __bytes__(self) -> bytes:
        if self.ptype == 'B':
            assert isinstance(self.value, int)
            return self.value.to_bytes(2, byteorder='big', signed=False)
        if self.ptype in {
            'F',
            '3',
        }:
            assert isinstance(self.value, int)
            return self.value.to_bytes(2, byteorder='big', signed=False)

        return super().__bytes__()


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


def realize_params_elvira(
    params: 'Iterable[str]',
    stream: IO[bytes],
    text_mask: int,
) -> 'Iterator[Param]':
    for ptype in params:
        if ptype == ' ':
            continue

        if ptype == 'B':
            val = read_uint16be(stream)
            yield ParamElvira(ptype, val)
            continue

        if ptype in {
            'F',
            '3',
        }:
            num = read_uint16be(stream)
            yield ParamElvira(ptype, num)
            continue

        yield from realize_params([ptype], stream, text_mask)


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
            special = special_items.get(num)
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
    (realize_params_func, command_type, sentinel, opsize) = (
        (realize_params_elvira, CommandElvira, CMD_EOL, 2)
        if parser.game == GameID.elvira1
        else (realize_params, Command, BYTE_MASK, 1)
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


def parse_args_elvira(
    cmds: 'Iterator[str]',
    params: 'Iterable[str]',
    text_mask: int,
) -> 'Iterator[Param]':
    for ptype in params:
        if ptype == ' ':
            continue

        if ptype == 'B':
            yield ParamElvira(ptype, int(next(cmds)))
            continue

        if ptype in {
            'F',
            '3',
        }:
            yield ParamElvira(ptype, int(next(cmds)))
            continue

        yield from parse_args(cmds, [ptype], text_mask)


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

        raise ValueError(ptype)


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
        sys.exit(1)


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
        (parse_args_elvira, CommandElvira)
        if parser.game == GameID.elvira1
        else (parse_args, Command)
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


def parse_object_property(
    aprops: 'dict[str, str]',
    game: 'GameID',
) -> 'Property':
    dprops: Property
    if game == GameID.elvira1:
        dprops = {
            'ptype': ItemType.OBJECT,
            'game': GameID.elvira1,
            'text1': Param('T', int(aprops['TEXT1'])),
            'text2': Param('T', int(aprops['TEXT2'])),
            'text3': Param('T', int(aprops['TEXT3'])),
            'text4': Param('T', int(aprops['TEXT4'])),
            'size': int(aprops['SIZE']),
            'weight': int(aprops['WEIGHT']),
            'flags': int(aprops['FLAGS']),
        }
    else:
        aname = aprops.pop('NAME', None)
        name = Param('T', int(aname)) if aname is not None else None
        dprops = {
            'ptype': ItemType.OBJECT,
            'name': name,
            'params': {PropertyType[pkey]: int(val) for pkey, val in aprops.items()},
        }
        desc = dprops['params'].get(PropertyType.DESCRIPTION)
        if desc is not None:
            dprops['params'][PropertyType.DESCRIPTION] = Param('T', desc)
    return dprops


def parse_room_property(
    aprops: 'dict[str, str]',
    game: 'GameID',
) -> 'Property':
    dprops: Property
    if game == GameID.elvira1:
        dprops = {
            'ptype': ItemType.ROOM,
            'game': GameID.elvira1,
            'short': Param('T', int(aprops['SHORT'])),
            'long': Param('T', int(aprops['LONG'])),
            'flags': int(aprops['FLAGS']),
        }
    else:
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
    return dprops


def parse_user_flag_property(
    aprops: 'dict[str, str]',
    game: 'GameID',
) -> 'Property':
    dprops: UserFlagProperty = {
        'ptype': ItemType.USERFLAG,
        'flag1': int(aprops['1']),
        'flag2': int(aprops['2']),
        'flag3': int(aprops['3']),
        'flag4': int(aprops['4']),
    }
    if game == GameID.elvira1:
        dprops = cast(ElviraUserFlagProperty, dprops)
        dprops.update(
            {
                'game': GameID.elvira1,
                'flag5': int(aprops['5']),
                'flag6': int(aprops['6']),
                'flag7': int(aprops['7']),
                'flag8': int(aprops['8']),
                'item1': int(aprops['ITEM1']),
                'item2': int(aprops['ITEM2']),
                'item3': int(aprops['ITEM3']),
                'item4': int(aprops['ITEM4']),
            }
        )
    return dprops


def parse_super_room_genexit_property(
    aprops: 'dict[str, str]',
    game: 'GameID',
) -> 'Property':
    dprops: Property
    if game == GameID.elvira1:
        dprops = {
            'ptype': ItemType.GENEXIT,
            'game': GameID.elvira1,
            'dest1': int(aprops['DEST1']),
            'dest2': int(aprops['DEST2']),
            'dest3': int(aprops['DEST3']),
            'dest4': int(aprops['DEST4']),
            'dest5': int(aprops['DEST5']),
            'dest6': int(aprops['DEST6']),
            'dest7': int(aprops['DEST7']),
            'dest8': int(aprops['DEST8']),
            'dest9': int(aprops['DEST9']),
            'dest10': int(aprops['DEST10']),
            'dest11': int(aprops['DEST11']),
            'dest12': int(aprops['DEST12']),
        }
    else:
        srid, x, y, z = (int(x) for x in aprops['SUPER_ROOM'].split())
        dprops = {
            'ptype': ItemType.SUPER_ROOM,
            'srid': srid,
            'x': x,
            'y': y,
            'z': z,
            'exits': [int(x) for x in aprops['EXITS'].split()],
        }
    return dprops


def parse_props(props: 'Iterable[str]', game: 'GameID') -> 'Iterator[Property]':
    for prop in props:
        rdtype, *rprops = prop.rstrip('\n').split('\n\t')
        dtype = ItemType[rdtype]
        aprops = dict(x.split(' //')[0].split(maxsplit=1) for x in rprops)
        dprops: Property
        if dtype == ItemType.OBJECT:
            dprops = parse_object_property(aprops, game)
        elif dtype == ItemType.ROOM:
            dprops = parse_room_property(aprops, game)
        elif dtype == ItemType.INHERIT:
            dprops = {
                'ptype': ItemType.INHERIT,
                'item': int(aprops['ITEM']),
            }
        elif dtype == ItemType.USERFLAG:
            dprops = parse_user_flag_property(aprops, game)
        elif dtype in {ItemType.SUPER_ROOM, ItemType.GENEXIT}:
            dprops = parse_super_room_genexit_property(aprops, game)
        elif dtype == ItemType.CONTAINER:
            dprops = {
                'ptype': ItemType.CONTAINER,
                'volume': int(aprops['VOLUME']),
                'flags': int(aprops['FLAGS']),
            }
        elif dtype == ItemType.CHAIN:
            dprops = {
                'ptype': ItemType.CHAIN,
                'item': int(aprops['ITEM']),
            }
        else:
            raise ValueError(dtype)
        yield dprops
