import os
import pathlib
import re

from magos.stream import read_uint32le, write_uint32le


MAX_VOICE_FILE_OFFSET = 2**17


def read_voc_offsets(stream, limit=MAX_VOICE_FILE_OFFSET):
    while stream.tell() < limit:
        offset = read_uint32le(stream)
        if offset > 0:
            limit = min(limit, offset)
        yield offset


def read_voc_soundbank(stream):
    offs = list(read_voc_offsets(stream))
    sizes = [(end - start) for start, end in zip(offs, offs[1:])] + [None]

    for idx, (offset, size) in enumerate(zip(offs, sizes)):
        if offset == 0:
            continue
        assert stream.tell() == offset, (stream.tell(), offset)
        if size is None or size > 0:
            yield idx, stream.read(size)


def extract_voices(voice_file, target_dir):
    target_dir = pathlib.Path(target_dir)
    _, ext = os.path.splitext(os.path.basename(voice_file))
    with open(voice_file, 'rb') as soundbank:
        os.makedirs(target_dir, exist_ok=True)
        for idx, vocdata in read_voc_soundbank(soundbank):
            (target_dir / f'{idx:04d}{ext}').write_bytes(vocdata)


def read_sounds(target_dir, ext, maxnum):
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


def rebuild_voices(voice_file, target_dir):
    target_dir = pathlib.Path(target_dir)
    base, ext = os.path.splitext(os.path.basename(voice_file))

    def extract_number(sfile):
        s = re.findall(f"(\d+).{ext}", sfile)
        return (int(s[0]) if s else -1, sfile)

    maxfile = max(os.listdir(target_dir), key=extract_number)
    maxnum = int(maxfile.removesuffix(ext))
    print(maxnum)
    offs, sounds = zip(*read_sounds(target_dir, ext, maxnum))
    pathlib.Path((base + ext)).write_bytes(
        b''.join(write_uint32le(offset) for offset in offs) + b''.join(sounds)
    )


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Process resources for Simon the Sorcerer.'
    )
    parser.add_argument(
        'filename',
        help='Path to the game data file to extract texts from (e.g. SIMON.VOC)',
    )

    args = parser.parse_args()
    extract_voices(args.filename, 'voices')
