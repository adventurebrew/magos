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
    ClassVar,
    Self,
    TextIO,
    TypedDict,
    cast,
    override,
)

from magos.detection import GameID
from magos.stream import (
    read_uint16be,
    read_uint32be,
    write_uint16be,
    write_uint32be,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

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


@dataclass
class Property:
    ptype_: ClassVar[ItemType]

    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        raise NotImplementedError

    def write_bytes(self) -> bytes:
        raise NotImplementedError

    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        raise NotImplementedError

    @classmethod
    def from_text(cls, lines: Sequence[str]) -> 'Self':
        props = dict(x.split(' //')[0].split(maxsplit=1) for x in lines)
        return cls.from_parsed(props)

    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        raise NotImplementedError


@dataclass
class RoomProperty(Property):
    ptype_: ClassVar[ItemType] = ItemType.ROOM

    table: int
    exits: Sequence[Exit | None]

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
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

        return cls(
            table=table,
            exits=exits,
        )

    @override
    def write_bytes(self) -> bytes:
        exit_states = 0
        sout = bytearray()
        for ex in self.exits[::-1]:
            exit_states <<= 2
            if ex is not None:
                assert ex['status'] != 0, ex
                sout = bytearray(write_item(ex['exit_to']) + sout)
                exit_states |= ex['status']
        return write_uint16be(self.table) + write_uint16be(exit_states) + bytes(sout)

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        exits = []
        for i in range(6):
            exd = props[f'EXIT{1+i}']
            ex: Exit | None
            if exd == '-':
                ex = None
            else:
                eto, status = exd.split()
                ex = {'exit_to': int(eto), 'status': DoorState[status]}
            exits.append(ex)
        return cls(
            table=int(props['TABLE']),
            exits=exits,
        )

    @override
    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        print('\tTABLE', self.table, file=output)
        for idx, ex in enumerate(self.exits):
            print(
                f'\tEXIT{1+idx}',
                f"{ex['exit_to']} {ex['status'].name}" if ex is not None else '-',
                file=output,
            )


@dataclass
class ObjectPropertyElvira2(Property):
    ptype_: ClassVar[ItemType] = ItemType.OBJECT
    params: 'dict[PropertyType, int | Param]'

    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> Self:
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

        return cls(
            params=params,
        )

    def write_bytes(self) -> bytes:
        params = dict(self.params)
        sout = bytearray()
        flags = cast(int, params.pop(PropertyType.FLAGS, 0)) << 16
        for key in PropertyType:
            val = params.pop(key, None)
            if val is not None:
                flags |= 2**key
                sout += (
                    write_uint32be(cast(Param, val).value)
                    if key == PropertyType.DESCRIPTION
                    else write_uint16be(cast(int, val))
                )
        assert not params, params
        return write_uint32be(flags) + bytes(sout)

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        params: dict[PropertyType, int | Param] = {
            PropertyType[pkey]: int(val) for pkey, val in props.items()
        }
        desc = params.get(PropertyType.DESCRIPTION)
        if desc is not None:
            params[PropertyType.DESCRIPTION] = Param('T', desc)
        return cls(params=params)

    @override
    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        description = self.params.pop(PropertyType.DESCRIPTION, None)
        if description:
            assert isinstance(description, Param)
            print(
                '\tDESCRIPTION',
                description.value,
                '//',
                resolve(description),
                file=output,
            )
        for pkey, pval in self.params.items():
            print(f'\t{pkey.name}', pval, file=output)


@dataclass
class ObjectProperty(ObjectPropertyElvira2):
    name: 'Param'

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        base = ObjectPropertyElvira2.from_bytes(stream, soundmap=soundmap)
        name = Param('T', read_uint32be(stream))
        return cls(
            params=base.params,
            name=name,
        )

    @override
    def write_bytes(self) -> bytes:
        return super().write_bytes() + write_uint32be(self.name.value)

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        name = Param('T', int(props.pop('NAME')))
        base = ObjectPropertyElvira2.from_parsed(props)
        return cls(
            params=base.params,
            name=name,
        )

    @override
    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        print(
            '\tNAME',
            self.name.value,
            '//',
            resolve(self.name),
            file=output,
        )
        super().write_text(output, resolve)


@dataclass
class SuperRoomProperty(Property):
    ptype_: ClassVar[ItemType] = ItemType.SUPER_ROOM

    srid: int
    x: int
    y: int
    z: int
    exits: Sequence[int]

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        srid = read_uint16be(stream)
        x = read_uint16be(stream)
        y = read_uint16be(stream)
        z = read_uint16be(stream)
        exits = [read_uint16be(stream) for _ in range(x * y * z)]
        return cls(
            srid=srid,
            x=x,
            y=y,
            z=z,
            exits=exits,
        )

    @override
    def write_bytes(self) -> bytes:
        return (
            write_uint16be(self.srid)
            + write_uint16be(self.x)
            + write_uint16be(self.y)
            + write_uint16be(self.z)
            + b''.join(write_uint16be(ex) for ex in self.exits)
        )

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        srid, x, y, z = (int(x) for x in props['SUPER_ROOM'].split())
        exits = [int(x) for x in props['EXITS'].split()]
        return cls(
            srid=srid,
            x=x,
            y=y,
            z=z,
            exits=exits,
        )

    @override
    def write_text(self, output: IO[str], resolve: 'Callable[[Param], str]') -> None:
        print(
            '\tSUPER_ROOM',
            self.srid,
            self.x,
            self.y,
            self.z,
            file=output,
        )
        print('\tEXITS', ' '.join(str(ex) for ex in self.exits), file=output)


@dataclass
class UserFlagProperty(Property):
    ptype_: ClassVar[ItemType] = ItemType.USERFLAG

    flag1: int
    flag2: int
    flag3: int
    flag4: int

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        return cls(
            flag1=read_uint16be(stream),
            flag2=read_uint16be(stream),
            flag3=read_uint16be(stream),
            flag4=read_uint16be(stream),
        )

    @override
    def write_bytes(self) -> bytes:
        return (
            write_uint16be(self.flag1)
            + write_uint16be(self.flag2)
            + write_uint16be(self.flag3)
            + write_uint16be(self.flag4)
        )

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        return cls(
            flag1=int(props['1']),
            flag2=int(props['2']),
            flag3=int(props['3']),
            flag4=int(props['4']),
        )

    @override
    def write_text(self, output: IO[str], resolve: 'Callable[[Param], str]') -> None:
        print('\t1', self.flag1, file=output)
        print('\t2', self.flag2, file=output)
        print('\t3', self.flag3, file=output)
        print('\t4', self.flag4, file=output)


@dataclass
class ContainerProperty(Property):
    ptype_: ClassVar[ItemType] = ItemType.CONTAINER

    volume: int
    flags: int

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        return cls(
            volume=read_uint16be(stream),
            flags=read_uint16be(stream),
        )

    @override
    def write_bytes(self) -> bytes:
        return write_uint16be(self.volume) + write_uint16be(self.flags)

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        return cls(
            volume=int(props['VOLUME']),
            flags=int(props['FLAGS']),
        )

    @override
    def write_text(self, output: IO[str], resolve: 'Callable[[Param], str]') -> None:
        print('\tVOLUME', self.volume, file=output)
        print('\tFLAGS', self.flags, file=output)
        # TODO: show actual flags values, from AberMUD V source:
        #       CO_SOFT		1	/* Item has size increased by contents  */
        #       CO_SEETHRU	2	/* You can see into the item		*/
        #       CO_CANPUTIN	4	/* For PUTIN action			*/
        #       CO_CANGETOUT	8	/* For GETOUT action			*/
        #       CO_CLOSES	16	/* Not state 0 = closed			*/
        #       CO_SEEIN	32	/* Container shows contents by		*/


@dataclass
class InheritProperty(Property):
    ptype_: ClassVar[ItemType] = ItemType.INHERIT

    item: int

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        return cls(
            item=read_item(stream),
        )

    @override
    def write_bytes(self) -> bytes:
        return write_item(self.item)

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        return cls(
            item=int(props['ITEM']),
        )

    @override
    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        print('\tITEM', self.item, file=output)


@dataclass
class ChainProperty(InheritProperty):
    ptype_: ClassVar[ItemType] = ItemType.CHAIN


@dataclass
class UserFlagPropertyElvira(UserFlagProperty):
    flag5: int
    flag6: int
    flag7: int
    flag8: int
    item1: int
    item2: int
    item3: int
    item4: int

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        base = UserFlagProperty.from_bytes(stream, soundmap=soundmap)
        return cls(
            flag1=base.flag1,
            flag2=base.flag2,
            flag3=base.flag3,
            flag4=base.flag4,
            flag5=read_uint16be(stream),
            flag6=read_uint16be(stream),
            flag7=read_uint16be(stream),
            flag8=read_uint16be(stream),
            item1=read_item(stream),
            item2=read_item(stream),
            item3=read_item(stream),
            item4=read_item(stream),
        )

    @override
    def write_bytes(self) -> bytes:
        return (
            super().write_bytes()
            + write_uint16be(self.flag5)
            + write_uint16be(self.flag6)
            + write_uint16be(self.flag7)
            + write_uint16be(self.flag8)
            + write_item(self.item1)
            + write_item(self.item2)
            + write_item(self.item3)
            + write_item(self.item4)
        )

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        base = UserFlagProperty.from_parsed(props)
        return cls(
            flag1=base.flag1,
            flag2=base.flag2,
            flag3=base.flag3,
            flag4=base.flag4,
            flag5=int(props['5']),
            flag6=int(props['6']),
            flag7=int(props['7']),
            flag8=int(props['8']),
            item1=int(props['ITEM1']),
            item2=int(props['ITEM2']),
            item3=int(props['ITEM3']),
            item4=int(props['ITEM4']),
        )

    @override
    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        super().write_text(output, resolve)
        print('\t5', self.flag5, file=output)
        print('\t6', self.flag6, file=output)
        print('\t7', self.flag7, file=output)
        print('\t8', self.flag8, file=output)
        print('\tITEM1', self.item1, file=output)
        print('\tITEM2', self.item2, file=output)
        print('\tITEM3', self.item3, file=output)
        print('\tITEM4', self.item4, file=output)


@dataclass
class ObjectPropertyElvira(Property):
    ptype_: ClassVar[ItemType] = ItemType.OBJECT

    text1: 'Param'
    text2: 'Param'
    text3: 'Param'
    text4: 'Param'
    size: int
    weight: int
    flags: int

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        text1 = Param('T', read_uint32be(stream))
        text2 = Param('T', read_uint32be(stream))
        text3 = Param('T', read_uint32be(stream))
        text4 = Param('T', read_uint32be(stream))
        size = read_uint16be(stream)
        weight = read_uint16be(stream)
        flags = read_uint16be(stream)
        return cls(
            text1=text1,
            text2=text2,
            text3=text3,
            text4=text4,
            size=size,
            weight=weight,
            flags=flags,
        )

    @override
    def write_bytes(self) -> bytes:
        return (
            write_uint32be(self.text1.value)
            + write_uint32be(self.text2.value)
            + write_uint32be(self.text3.value)
            + write_uint32be(self.text4.value)
            + write_uint16be(self.size)
            + write_uint16be(self.weight)
            + write_uint16be(self.flags)
        )

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        return cls(
            text1=Param('T', int(props['TEXT1'])),
            text2=Param('T', int(props['TEXT2'])),
            text3=Param('T', int(props['TEXT3'])),
            text4=Param('T', int(props['TEXT4'])),
            size=int(props['SIZE']),
            weight=int(props['WEIGHT']),
            flags=int(props['FLAGS']),
        )

    @override
    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        print('\tTEXT1', self.text1.value, '//', resolve(self.text1), file=output)
        print('\tTEXT2', self.text2.value, '//', resolve(self.text2), file=output)
        print('\tTEXT3', self.text3.value, '//', resolve(self.text3), file=output)
        print('\tTEXT4', self.text4.value, '//', resolve(self.text4), file=output)
        print('\tSIZE', self.size, file=output)
        print('\tWEIGHT', self.weight, file=output)
        print('\tFLAGS', self.flags, file=output)


@dataclass
class GenExitProperty(Property):
    ptype_: ClassVar[ItemType] = ItemType.GENEXIT

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

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        return cls(
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

    @override
    def write_bytes(self) -> bytes:
        return (
            write_item(self.dest1)
            + write_item(self.dest2)
            + write_item(self.dest3)
            + write_item(self.dest4)
            + write_item(self.dest5)
            + write_item(self.dest6)
            + write_item(self.dest7)
            + write_item(self.dest8)
            + write_item(self.dest9)
            + write_item(self.dest10)
            + write_item(self.dest11)
            + write_item(self.dest12)
        )

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        return cls(
            dest1=int(props['DEST1']),
            dest2=int(props['DEST2']),
            dest3=int(props['DEST3']),
            dest4=int(props['DEST4']),
            dest5=int(props['DEST5']),
            dest6=int(props['DEST6']),
            dest7=int(props['DEST7']),
            dest8=int(props['DEST8']),
            dest9=int(props['DEST9']),
            dest10=int(props['DEST10']),
            dest11=int(props['DEST11']),
            dest12=int(props['DEST12']),
        )

    @override
    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        print('\tDEST1', self.dest1, file=output)
        print('\tDEST2', self.dest2, file=output)
        print('\tDEST3', self.dest3, file=output)
        print('\tDEST4', self.dest4, file=output)
        print('\tDEST5', self.dest5, file=output)
        print('\tDEST6', self.dest6, file=output)
        print('\tDEST7', self.dest7, file=output)
        print('\tDEST8', self.dest8, file=output)
        print('\tDEST9', self.dest9, file=output)
        print('\tDEST10', self.dest10, file=output)
        print('\tDEST11', self.dest11, file=output)
        print('\tDEST12', self.dest12, file=output)


@dataclass
class RoomPropertyElvira(Property):
    ptype_: ClassVar[ItemType] = ItemType.ROOM

    short: 'Param'
    long: 'Param'
    flags: int

    @override
    @classmethod
    def from_bytes(
        cls,
        stream: IO[bytes],
        soundmap: dict[int, set[int]] | None = None,
    ) -> 'Self':
        short = Param('T', read_uint32be(stream))
        long = Param('T', read_uint32be(stream))
        flags = read_uint16be(stream)
        return cls(
            short=short,
            long=long,
            flags=flags,
        )

    @override
    def write_bytes(self) -> bytes:
        return (
            write_uint32be(self.short.value)
            + write_uint32be(self.long.value)
            + write_uint16be(self.flags)
        )

    @override
    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        return cls(
            short=Param('T', int(props['SHORT'])),
            long=Param('T', int(props['LONG'])),
            flags=int(props['FLAGS']),
        )

    @override
    def write_text(
        self,
        output: IO[str],
        resolve: 'Callable[[Param], str]',
    ) -> None:
        print('\tSHORT', self.short.value, '//', resolve(self.short), file=output)
        print('\tLONG', self.long.value, '//', resolve(self.long), file=output)
        print('\tFLAGS', self.flags, file=output)


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
    mapping = get_property_mapping(game)

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
            properties.append(mapping[ptype].from_bytes(stream, soundmap=soundmap))
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
            output += write_uint16be(prop.ptype_.value) + prop.write_bytes()
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
                value = write_item(int(self.value[1:-1]))
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
                num = read_item(stream)
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


def get_property_mapping(game: 'GameID') -> dict[ItemType, type[Property]]:
    if game == GameID.elvira1:
        return {
            ItemType.INHERIT: InheritProperty,
            ItemType.CONTAINER: ContainerProperty,
            ItemType.USERFLAG: UserFlagPropertyElvira,
            ItemType.OBJECT: ObjectPropertyElvira,
            ItemType.ROOM: RoomPropertyElvira,
            ItemType.GENEXIT: GenExitProperty,
            ItemType.CHAIN: ChainProperty,
        }
    return {
        ItemType.ROOM: RoomProperty,
        ItemType.OBJECT: (
            ObjectPropertyElvira2 if game <= GameID.elvira2 else ObjectProperty
        ),
        # ItemType.PLAYER: None,
        ItemType.SUPER_ROOM: SuperRoomProperty,
        # ItemType.CONTAINER: ContainerProperty,
        # ItemType.CHAIN: ChainProperty,
        ItemType.USERFLAG: UserFlagProperty,
        ItemType.INHERIT: InheritProperty,
    }


def parse_props(props: 'Iterable[str]', game: 'GameID') -> 'Iterator[Property]':
    mapping = get_property_mapping(game)
    for prop in props:
        rdtype, *rprops = prop.rstrip('\n').split('\n\t')
        dtype = ItemType[rdtype]
        yield mapping[dtype].from_text(rprops)
