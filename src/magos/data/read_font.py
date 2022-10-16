import numpy as np
import pathlib

from PIL import Image

from magos.stream import read_uint16le, read_uint32le, write_uint16le, write_uint32le
from magos.zone import get_zone_filenames
from .image_reader import read_image_grid, resize_frame


def decode_vga_font(h, w, data, color=1):
    # buffer = bytes(
    #     0 if c == 0
    #     else 207 if c == 0xF
    #     else c + color
    #     for c in data
    # )
    return np.frombuffer(data, dtype=np.uint8).reshape(h, w)


def read_feeble_vga_font():
    _vga1_filename, vga2_filename = get_zone_filenames(2)
    with open(vga2_filename, 'rb') as vga2_file:
        vga2_file.seek(96)
        chars = []
        for i in range(ord(' '), ord('z') + 1):
            img = read_uint32le(vga2_file)
            height = read_uint16le(vga2_file)
            width = read_uint16le(vga2_file)
            chars.append((chr(i), img, height, width))

        vga2_file.seek(chars[1][1], 0)

        for ch, off, h, w in chars:
            if h == 0 or w == 0:
                continue

            assert vga2_file.tell() == off, (vga2_file.tell(), off)
            vga2_file.seek(off, 0)
            yield ch, decode_vga_font(h, w, vga2_file.read(w * h))


def read_simon_vga_font():
    _vga1_filename, vga2_filename = get_zone_filenames(2)
    with open(vga2_filename, 'rb') as vga2_file:
        vga2_file.seek(48)
        chars = []
        for i in range(ord(' '), ord('z') + 1):
            img = read_uint16le(vga2_file)
            height, width = vga2_file.read(2)
            chars.append((chr(i), img, height, width))

        vga2_file.seek(chars[0][1], 0)

        for ch, off, h, w in chars:
            print(ch, off, h, w)
            if h == 0 or w == 0:
                continue
            assert vga2_file.tell() == off, (vga2_file.tell(), off)
            vga2_file.seek(off, 0)
            yield ch, decode_vga_font(h, w, vga2_file.read(w * h))


def convert_to_pil_image(liner, width, height):
    npp = np.array([ord(x) for x in liner], dtype=np.uint8)
    npp.resize(height, width)
    im = Image.fromarray(npp, mode='P')
    return im


def get_bg_color(row_size, f):
    BGS = ['0', 'n']

    def get_bg(idx):
        return BGS[f(idx) % len(BGS)]

    return get_bg


def resize_pil_image(w, h, bg, im):
    nbase = convert_to_pil_image(str(bg) * w * h, w, h)
    # nbase.paste(im, box=itemgetter('x1', 'y1', 'x2', 'y2')(loc))
    nbase.paste(im, box=(0, 0))
    return nbase


if __name__ == '__main__':

    # SUBTITLES FONT FROM VGA
    w = 16
    h = 16
    grid_size = 16

    enpp = np.array([[0xF] * w * grid_size] * h * grid_size, dtype=np.uint8)
    bim = Image.fromarray(enpp, mode='P')

    get_bg = get_bg_color(grid_size, lambda idx: idx + int(idx / grid_size))

    images = {}

    osum = 0
    for ch, image in read_feeble_vga_font():
        idx = ord(ch)
        images[idx] = image
        osum += image.shape[1]
        im = resize_pil_image(w, h, get_bg(idx), Image.fromarray(image, mode='P'))
        bim.paste(im, box=((idx % grid_size) * w, int(idx / grid_size) * h))

    bim.save('font.png')

    # INJECT

    frames = read_image_grid('../fonts/font_feeble_he.png')
    # frames = read_image_grid('font.png')
    frames = (resize_frame(frame) for frame in frames)
    tsum = 0
    output_idx = bytearray()
    output_data = bytearray()
    num_chars = len(range(ord(' '), ord('z') + 1))
    offset = 0xB300  # vga2_file.block_end
    for idx, frame in enumerate(frames):
        if idx < 32:
            continue
        if frame is not None:
            w, frame = frame
            frame = np.asarray(frame, dtype=np.uint8)
            # assert np.array_equal(frame, images.get(idx))
            print(idx, repr(chr(idx)), frame, images.get(idx))
            h, wi = frame.shape
            assert w == wi, (w, wi)
            tsum += w
            frame_data = bytes(frame.ravel())
            output_idx += write_uint32le(offset) + write_uint16le(h) + write_uint16le(w)
            output_data += frame_data
            assert len(frame_data) == w * h, (len(frame_data), w * h, frame.shape)
            offset += len(frame_data)
        else:
            output_idx += b'\0' * 8
    print(osum, tsum)

    _vga1_filename, vga2_filename = get_zone_filenames(2)

    vga_data = bytearray(pathlib.Path(vga2_filename).read_bytes())
    vga_data[96 : 96 + 8 * num_chars] = output_idx
    vga_data[0xB300:] = output_data

    pathlib.Path('0022-NEW.VGA').write_bytes(vga_data)
