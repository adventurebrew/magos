# -*- coding: windows-1255 -*-
import struct
import os
import errno
import sys

def hebrew_char_map():
    charMap = {'@': 'א', 'A': 'ב', 'B': 'ג',
               'C': 'ד', 'D': 'ה', 'E': 'ו',
               'F': 'ז', 'G': 'ח', 'H': 'ט',
               'I': 'י', 'J': 'ך', 'K': 'כ',
               'L': 'ל', 'M': 'ם', 'N': 'מ',
               'O': 'ן', 'P': 'נ', 'Q': 'ס',
               'R': 'ע', 'S': 'ף', 'T': 'פ',
               'U': 'ץ', 'V': 'צ', 'W': 'ק',
               'X': 'ר', 'Y': 'ש', 'Z': 'ת'}
    return lambda c: charMap[c] if c in charMap else c

def identity_map():
    return lambda c: c

def readcstr(f, map_char):
    buf = bytearray()
    while True:
        b = f.read(1)
        if b is None or b == '\0' or not b:
            return str(buf)
        else:
            buf.append(map_char(b))

def create_directory(name):
    try:
        os.makedirs(name)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def splitbins(input_file):
    create_directory('temps')
    with open(input_file, 'rb') as gmeFile:
        offsets = []
        offsets.append(struct.unpack('<I', gmeFile.read(4))[0])
        while gmeFile.tell() < offsets[0]:
            offsets.append(struct.unpack('<I', gmeFile.read(4))[0])

        for idx, offset in enumerate(offsets[:-1]):
            with open('temps/tempfile{:04}.bin'.format(idx), 'wb') as tempFile:
                tempFile.write(gmeFile.read(offsets[idx + 1] - offset))

        with open('temps/tempfile{:04}.bin'.format(len(offsets)), 'wb') as tempFile:
                tempFile.write(gmeFile.read())
    return offsets

def index_text_files():
    textFiles = []
    with open('STRIPPED.TXT', 'rb') as strpFile:
        while True:
            name = strpFile.read(7)
            if not name:
                break
            unknown = struct.unpack('<I', strpFile.read(1) + '\x00\x00\x00')[0]
            offsetProbably = struct.unpack('<I', strpFile.read(1) + '\x00\x00\x00')[0]
            textFiles.append(name)
    return textFiles

def make_texts(offsets, textFiles, map_char):
    create_directory('texts')
    with open('offsets.txt', 'w') as offFile:
        last = 0
        for idx, off in enumerate(offsets):
            offFile.write('{} - {}: {} - {} = {} \n'.format(idx, hex(idx), off, hex(off), last == off))
            last = off

    files = os.listdir('temps')
    texts = files[366 : 366 + len(textFiles)]

    for idx, f in enumerate(texts):
        with open('temps/' + f, 'rb') as tempFile, open('texts/' + textFiles[idx][:-1] + '.txt', 'wb') as strFile:
            while True:
                strr = readcstr(tempFile, map_char)
                if not strr:
                    break
                strFile.write(str(strr + '\r\n'))

if __name__ == '__main__':
    map_char = identity_map()
    filename = 'SIMON.GME'
    try:
        filename = sys.argv[1]
        if filename in ('--decrypt', '-d'):
            if sys.argv[2] == 'he':
                map_char = hebrew_char_map()
            else:
                raise IndexError
            filename = sys.argv[3]
    except IndexError as e:
        print('Usage:\n' + 'python split-gme.py [--decrypt he] SIMON.GME')
        exit(1)

    if not os.path.exists(filename):
        print('Error: file \'{}\' does not exists.'.format(filename))
        exit(1)

    offsets = splitbins(filename)
    textFiles = index_text_files()
    make_texts(offsets, textFiles, map_char)
