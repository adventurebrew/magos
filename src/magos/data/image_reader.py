#!/usr/bin/env python3

from itertools import takewhile
from struct import Struct

import numpy as np
from PIL import Image

PALETTE_SIZE = 256
palette_struct = Struct('<{}B'.format(3 * PALETTE_SIZE))


def read_image_grid(filename):
    w = 16
    h = 16

    bim = Image.open(filename)

    # mode = bim.mode
    # print((mode))
    # if mode != 'P':
    #     bim.convert('P')

    # color_mode, palette = bim.palette.getdata()
    # palette = palette_struct.unpack(palette)
    # palette = list(zip(*[iter(palette)]*3)) #[palette[3*i:3*i+3] for i in range(256)]

    for row in range(16):
        for col in range(16):
            area = (col * w, row * h, (col + 1) * w, (row + 1) * h)
            yield bim.crop(area)


def count_in_row(pred, row):
    return sum(1 for _ in takewhile(pred, row))


def resize_frame(im):
    BGS = [ord('0'), ord('n')]
    char_is_bg = lambda c: c in BGS
    line_is_bg = lambda line: all(c in BGS for c in line)

    frame = list(np.asarray(im))

    # h1 = count_in_row(search_line, frame)
    # h2 = count_in_row(search_line, frame[h1 + 1:])
    # print(h1, h2)
    charWidth = len(frame[0]) - min(
        count_in_row(char_is_bg, reversed(line)) for line in frame
    )
    h3 = len(frame) - count_in_row(line_is_bg, reversed(frame))

    area = (0, 0, charWidth, h3)

    if area == (0, 0, len(frame[0]), len(frame)):
        return None

    # fields = ('x1', 'y1', 'x2', 'y2')
    # loc = dict(zip(fields, area))

    return charWidth, list(np.asarray(im.crop(area)))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='read smush file')
    parser.add_argument('filename', help='filename to read from')
    args = parser.parse_args()

    frames = read_image_grid(args.filename)
    frames = (resize_frame(frame) for frame in frames)
    for frame in frames:
        print(frame)
