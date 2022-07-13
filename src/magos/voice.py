import os
import pathlib

from magos.stream import read_uint32le


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

    target_dir = pathlib.Path('voices')
    base, ext = os.path.splitext(os.path.basename(args.filename))
    with open(args.filename, 'rb') as soundbank:
        os.makedirs(target_dir, exist_ok=True)
        for idx, vocdata in read_voc_soundbank(soundbank):
            (target_dir / f'{idx:04d}{ext}').write_bytes(vocdata)
