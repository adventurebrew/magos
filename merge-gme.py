# -*- coding: windows-1255 -*-
import struct
import os
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
    charMap = {v: k for k, v in charMap.iteritems()}
    return lambda c: charMap[c] if c in charMap else c

def identity_map():
    return lambda c: c

def collect_texts(map_char):
    texts = os.listdir('texts')
    files = os.listdir('temps')
    texts_start = 366 # find out why
    textbins = files[texts_start : texts_start + len(texts)]
    for idx, text in enumerate(texts):
        with open('texts/' + text, 'rb') as textFile, open('temps/' + textbins[idx], 'wb') as binFile:
            lines = textFile.readlines()
            for line in lines:
                line = line.rstrip('\r\n')
                line = ''.join(map_char(b) for b in line)
                binFile.write(line)
                binFile.write('\0')

def merge_files():
    files = os.listdir('temps')
    with open('TEMP_DAT', 'wb') as datFile, open('TEMP_IDX', 'wb') as idxFile:
        num = len(files)
        size = num * 4
        idxFile.write(struct.pack('<I', size))
        for f in files[:-1]:
            with open('temps/' + f, 'rb') as tempFile:
                datFile.write(tempFile.read())
                size += tempFile.tell()
            idxFile.write(struct.pack('<I', size))
        with open('temps/' + files[-1], 'rb') as tempFile:
            datFile.write(tempFile.read())

def write_output(filename):
    with open('TEMP_DAT', 'rb') as datFile, open('TEMP_IDX', 'rb') as idxFile, open(filename, 'wb') as gmeFile:
        gmeFile.write(idxFile.read())
        gmeFile.write(datFile.read())

if __name__ == '__main__':
    map_char = identity_map()
    filename = 'SIMON-NEW.GME'
    try:
        filename = sys.argv[1]
        if filename in ('--decrypt', '-d'):
            if sys.argv[2] == 'he':
                map_char = hebrew_char_map()
            else:
                raise IndexError
            filename = sys.argv[3]
    except IndexError as e:
        print('Usage:\n' + 'python merge-gme.py [--decrypt he] SIMON-NEW.GME')
        exit(1)

    if filename in ('', '.', '..', '/'):
        print('Error: can\'t create file without name')
        exit(1)

    collect_texts(map_char)
    merge_files()
    write_output()
