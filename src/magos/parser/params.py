from dataclasses import dataclass
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
)

from magos.stream import (
    read_uint16be,
    read_uint32be,
    write_uint32be,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping


BASE_MIN = 0x8000

DWORD_MASK = 0xFFFFFFFF
WORD_MASK = 0xFFFF
BYTE_MASK = 0xFF


def read_item(stream: IO[bytes]) -> int:
    val = read_uint32be(stream)
    return 0 if val == DWORD_MASK else val + 2


def write_item(num: int) -> bytes:
    return write_uint32be(DWORD_MASK if num == 0 else num - 2)


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

    @classmethod
    def from_bytes(
        cls,
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
                yield cls(ptype, num, text_mask)
                continue

            if ptype == 'B':
                num = ord(stream.read(1))
                yield (
                    cls(ptype, [ord(stream.read(1))])
                    if num == BYTE_MASK
                    else cls(ptype, num)
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
                    yield cls(ptype, special)
                else:
                    assert num == 0, num
                    num = read_item(stream)
                    yield cls(ptype, f'<{num}>')
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
                yield cls(ptype, num)
                continue

            raise NotImplementedError(ptype)

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

    @classmethod
    def from_parsed(
        cls,
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
                yield cls(ptype, num, text_mask)
                continue

            if ptype == 'B':
                rnum = next(cmds)
                stripped = rnum.strip('[]')
                if stripped != rnum:
                    yield cls(ptype, [int(stripped)])
                else:
                    yield cls(ptype, int(rnum))
                continue

            if ptype == 'I':
                yield cls(ptype, next(cmds))
                continue

            if ptype in {
                'v',
                'p',
                'n',
                'a',
                'S',
                'N',
            }:
                yield cls(ptype, int(next(cmds)))
                continue

            raise ValueError(ptype)


@dataclass
class ParamElvira(Param):
    @classmethod
    def from_bytes(
        cls,
        params: 'Iterable[str]',
        stream: IO[bytes],
        text_mask: int,
    ) -> 'Iterator[Param]':
        for ptype in params:
            if ptype == ' ':
                continue

            if ptype == 'B':
                val = read_uint16be(stream)
                yield cls(ptype, val)
                continue

            if ptype in {
                'F',
                '3',
            }:
                num = read_uint16be(stream)
                yield cls(ptype, num)
                continue
            yield from super().from_bytes([ptype], stream, text_mask)

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

    @classmethod
    def from_parsed(
        cls,
        cmds: 'Iterator[str]',
        params: 'Iterable[str]',
        text_mask: int,
    ) -> 'Iterator[Param]':
        for ptype in params:
            if ptype == ' ':
                continue

            if ptype == 'B':
                yield cls(ptype, int(next(cmds)))
                continue

            if ptype in {
                'F',
                '3',
            }:
                yield cls(ptype, int(next(cmds)))
                continue

            yield from super().from_parsed(cmds, [ptype], text_mask)
