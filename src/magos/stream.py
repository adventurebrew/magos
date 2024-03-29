import operator
import os
import struct
from functools import partial
from itertools import takewhile
from typing import IO, cast

UINT16BE = struct.Struct('>H')
UINT16LE = struct.Struct('<H')
UINT32BE = struct.Struct('>I')
UINT32LE = struct.Struct('<I')

SINT16BE = struct.Struct('>h')
SINT32BE = struct.Struct('>i')

FilePath = str | os.PathLike[str]


def read_uint32be(stream: IO[bytes]) -> int:
    return cast(int, UINT32BE.unpack(stream.read(UINT32BE.size))[0])


def read_sint32be(stream: IO[bytes]) -> int:
    return cast(int, SINT32BE.unpack(stream.read(SINT32BE.size))[0])


def read_sint16be(stream: IO[bytes]) -> int:
    return cast(int, SINT16BE.unpack(stream.read(SINT16BE.size))[0])


def read_uint32le(stream: IO[bytes]) -> int:
    return cast(int, UINT32LE.unpack(stream.read(UINT32LE.size))[0])


def read_uint16be(stream: IO[bytes]) -> int:
    return cast(int, UINT16BE.unpack(stream.read(UINT16BE.size))[0])


def read_uint16le(stream: IO[bytes]) -> int:
    return cast(int, UINT16LE.unpack(stream.read(UINT16LE.size))[0])


def write_uint32be(num: int) -> bytes:
    return UINT32BE.pack(num)


def write_uint32le(num: int) -> bytes:
    return UINT32LE.pack(num)


def write_uint16be(num: int) -> bytes:
    return UINT16BE.pack(num)


def write_uint16le(num: int) -> bytes:
    return UINT16LE.pack(num)


def readcstr(stream: IO[bytes]) -> bytes:
    toeof = iter(partial(stream.read, 1), b'')
    return b''.join(takewhile(partial(operator.ne, b'\00'), toeof))


def create_directory(name: FilePath) -> None:
    os.makedirs(name, exist_ok=True)
