# -*- coding: windows-1255 -*-
import struct
import os

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

texts = os.listdir('texts')
files = os.listdir('temps')
textbins = files[366 : 366 + len(texts)]

for idx, text in enumerate(texts):
    with open('texts/' + text, 'rb') as textFile, open('temps/' + textbins[idx], 'wb') as binFile:
        lines = textFile.readlines()
        for line in lines:
            line = line.strip()
            line = ''.join(charMap[b] if b in charMap else b for b in line)
            binFile.write(line)
            binFile.write('\0')


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

with open('TEMP_DAT', 'rb') as datFile, open('TEMP_IDX', 'rb') as idxFile, open('SIMON-NEW.GME', 'wb') as gmeFile:
    gmeFile.write(idxFile.read())
    gmeFile.write(datFile.read())
