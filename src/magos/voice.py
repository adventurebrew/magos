import os
import re
from itertools import pairwise
from pathlib import Path
from typing import IO, TYPE_CHECKING

from magos.stream import read_uint32le, write_uint32le

if TYPE_CHECKING:
    from collections.abc import Iterator

    from magos.stream import FilePath

MAX_VOICE_FILE_OFFSET = 2**17


def read_voc_offsets(
    stream: IO[bytes],
    limit: int = MAX_VOICE_FILE_OFFSET,
) -> 'Iterator[int]':
    while stream.tell() < limit:
        offset = read_uint32le(stream)
        if offset > 0:
            limit = min(limit, offset)
        yield offset


def read_voc_soundbank(stream: IO[bytes]) -> 'Iterator[tuple[int, bytes]]':
    offs = list(read_voc_offsets(stream))
    sizes = [(end - start) for start, end in pairwise(offs)] + [None]

    for idx, (offset, size) in enumerate(zip(offs, sizes, strict=True)):
        if offset == 0:
            continue
        assert stream.tell() == offset, (stream.tell(), offset)
        if size is None or size > 0:
            yield idx, stream.read(size)  # type: ignore[arg-type]


def extract_voices(voice_file: 'FilePath', target_dir: 'FilePath') -> None:
    target_dir = Path(target_dir)
    voice_file = Path(voice_file)
    ext = voice_file.suffix
    with voice_file.open('rb') as soundbank:
        os.makedirs(target_dir, exist_ok=True)
        for idx, vocdata in read_voc_soundbank(soundbank):
            (target_dir / f'{idx:04d}{ext}').write_bytes(vocdata)


def read_sounds(
    target_dir: Path,
    ext: str,
    maxnum: int,
) -> 'Iterator[tuple[int, bytes]]':
    start_offset = 4 * (maxnum + 1)
    offset = start_offset
    for idx in range(maxnum + 1):
        sfile = target_dir / f'{idx:04d}{ext}'
        content = b''
        if sfile.exists():
            content = sfile.read_bytes()
        if offset + len(content) > start_offset:
            yield offset, content
        else:
            yield 0, b''
        offset += len(content)


def rebuild_voices(voice_file: 'FilePath', target_dir: 'FilePath') -> None:
    target_dir = Path(target_dir)
    voice_file = Path(Path(voice_file).name)
    ext = voice_file.suffix

    def extract_number(sfile: str) -> tuple[int, str]:
        s = re.findall(rf'(\d+).{ext}', sfile)
        return (int(s[0]) if s else -1, sfile)

    maxfile = max(os.listdir(target_dir), key=extract_number)
    maxnum = int(maxfile.removesuffix(ext))
    offs, sounds = zip(*read_sounds(target_dir, ext, maxnum), strict=True)
    voice_file.write_bytes(
        b''.join(write_uint32le(offset) for offset in offs) + b''.join(sounds),
    )


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Process resources for Simon the Sorcerer.',
    )
    parser.add_argument(
        'filename',
        help='Path to the game data file to extract texts from (e.g. SIMON.VOC)',
    )

    args = parser.parse_args()
    extract_voices(args.filename, 'voices')
