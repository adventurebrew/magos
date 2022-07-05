import os
import pathlib

from magos.stream import read_uint32le


def read_voc_soundbank(stream):
    table_offset, data_offset = read_uint32le(stream), read_uint32le(stream)
    assert table_offset == 0, table_offset
    assert data_offset % 4 == 0, data_offset
    assert stream.tell() == 8
    num_sounds = (data_offset - stream.tell()) // 4
    offs = [data_offset] + [read_uint32le(stream) for _ in range(num_sounds)]
    sizes = [(end - start) for start, end in zip(offs, offs[1:])] + [None]
    assert stream.tell() == offs[0] == data_offset
    
    for idx, (offset, size) in enumerate(zip(offs, sizes), start=1):
        assert stream.tell() == offset, (stream.tell(), offset)
        if size is None or size > 0:
            yield idx, stream.read(size)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Process resources for Simon the Sorcerer.')
    parser.add_argument('filename', help='Path to the game data file to extract texts from (e.g. SIMON.VOC)')

    args = parser.parse_args()

    target_dir = pathlib.Path('voices')
    base, ext = os.path.splitext(os.path.basename(args.filename))
    with open(args.filename, 'rb') as soundbank:
        os.makedirs(target_dir, exist_ok=True)
        for idx, vocdata in read_voc_soundbank(soundbank):
            (target_dir / f'{idx:04d}{ext}').write_bytes(vocdata)
