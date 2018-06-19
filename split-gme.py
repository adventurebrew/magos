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

def splitbins(input_file, filenames):
    create_directory('temps')
    with open(input_file, 'rb') as gmeFile:
        offsets = []
        offsets.append(struct.unpack('<I', gmeFile.read(4))[0])
        while gmeFile.tell() < offsets[0]:
            offsets.append(struct.unpack('<I', gmeFile.read(4))[0])

        for idx, offset in enumerate(offsets[:-1]):
            filename = filenames[idx] if len(filenames) > idx else 'tempfile{:04}.bin'.format(idx)
            with open('temps/' + filename, 'wb') as tempFile:
                tempFile.write(gmeFile.read(offsets[idx + 1] - offset))

        with open('temps/ZZZ{:d}'.format(len(offsets)), 'wb') as tempFile:
                tempFile.write(gmeFile.read())
    return offsets

def index_table_files():
    # tableFiles = []
    # with open('TBLLIST', 'rb') as strpFile:
        # while True:
            # TO DO
    # return tableFiles
    return ['TABLES{:02}'.format(idx) for idx in range(1,31)]

def index_text_files():
    textFiles = []
    with open('STRIPPED.TXT', 'rb') as strpFile:
        while True:
            name = strpFile.read(7)
            if not name:
                break
            unknown = struct.unpack('<I', strpFile.read(1) + '\x00\x00\x00')[0]
            offsetProbably = struct.unpack('<I', strpFile.read(1) + '\x00\x00\x00')[0]
            textFiles.append(name[:-1])
    return textFiles

def make_texts(offsets, textFiles, map_char):
    create_directory('texts')

    for f in textFiles:
        with open('temps/' + f, 'rb') as tempFile, open('texts/' + f + '.txt', 'wb') as strFile:
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


    # this is specific to Simon the Sorcerer 1
    vgaf = ('{:03d}'.format(idx) for idx in range(164))
    vgas = [item for it in ((vga + '1.VGA', vga + '2.VGA') for vga in vgaf) for item in it]
    unknown = ['UNKNOWN.BIN'] # unknown file
    muses = ['MOD{:d}.MUS'.format(idx) for idx in range(36)]
    empty = ['EMPTYFILE']
    textFiles = index_text_files()
    tableFiles = index_table_files()

    filenames = vgas + unknown + muses + empty + textFiles + tableFiles + empty # there will be another empty file at the end

    offsets = splitbins(filename, filenames)

    # print information to file to help tracking
    with open('offsets.txt', 'w') as offFile:
        last = 0
        for idx, off in enumerate(offsets):
            offFile.write('{} - {}: {} - {} = {} | {} \n'.format(idx, hex(idx), off, hex(off), last == off, filenames[idx] if idx < len(filenames) else 'TEMPFILE{:03d}'.format(idx)))
            last = off

    make_texts(offsets, textFiles, map_char)
