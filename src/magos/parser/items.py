import io
from dataclasses import dataclass
from enum import IntEnum
from typing import IO, TYPE_CHECKING, ClassVar, TypedDict, cast, override

from magos.detection import GameID
from magos.parser.params import Param, read_item, write_item
from magos.stream import (
    read_uint16be,
    read_uint32be,
    write_uint16be,
    write_uint32be,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from typing import Self


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

    def __bytes__(self) -> bytes:
        raise NotImplementedError

    @classmethod
    def from_parsed(cls, props: dict[str, str]) -> 'Self':
        raise NotImplementedError

    @classmethod
    def from_text(cls, lines: 'Sequence[str]') -> 'Self':
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
    exits: 'Sequence[Exit | None]'

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
    def __bytes__(self) -> bytes:
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
    ) -> 'Self':
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

    def __bytes__(self) -> bytes:
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
    def __bytes__(self) -> bytes:
        return super().__bytes__() + write_uint32be(self.name.value)

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
    exits: 'Sequence[int]'

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
    def __bytes__(self) -> bytes:
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
    def __bytes__(self) -> bytes:
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
    def __bytes__(self) -> bytes:
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
    def __bytes__(self) -> bytes:
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
    def __bytes__(self) -> bytes:
        return (
            super().__bytes__()
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
    def __bytes__(self) -> bytes:
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
    def __bytes__(self) -> bytes:
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
    def __bytes__(self) -> bytes:
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
    properties: 'Sequence[Property]'
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
) -> 'Sequence[Item]':
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
            output += write_uint16be(prop.ptype_.value) + bytes(prop)
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


def write_objects_text(
    objects: 'Sequence[Item]',
    output_file: 'IO[str]',
    resolve: 'Callable[[Param], str]',
) -> None:
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
            print(f'==> {prop.ptype_.name}', file=output_file)
            prop.write_text(output_file, resolve)


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
            'Item',
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
