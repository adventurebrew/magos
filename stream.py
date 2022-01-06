import operator
import os
import struct
from functools import partial
from itertools import takewhile
from typing import IO

UINT16BE = struct.Struct('>H')
UINT32BE = struct.Struct('>I')
UINT32LE = struct.Struct('<I')
SINT32BE = struct.Struct('>i')

def read_uint32be(stream: IO[bytes]) -> int:
    return UINT32BE.unpack(stream.read(UINT32BE.size))[0]


def read_uint32le(stream: IO[bytes]) -> int:
    return UINT32LE.unpack(stream.read(UINT32LE.size))[0]


def read_uint16be(stream: IO[bytes]) -> int:
    return UINT16BE.unpack(stream.read(UINT16BE.size))[0]


def write_uint32be(num: int) -> bytes:
    return UINT32BE.pack(num)


def write_uint32le(num: int) -> bytes:
    return UINT32LE.pack(num)


def write_uint16be(num: int) -> bytes:
    return UINT16BE.pack(num)

def readcstr(stream: IO[bytes]) -> bytes:
    toeof = iter(partial(stream.read, 1), b'')
    return b''.join(takewhile(partial(operator.ne, b'\00'), toeof))


def create_directory(name: str) -> None:
    os.makedirs(name, exist_ok=True)
