# -*- coding: windows-1255 -*-
import struct
import os

charMap = {'@': '�', 'A': '�', 'B': '�',
           'C': '�', 'D': '�', 'E': '�',
           'F': '�', 'G': '�', 'H': '�',
           'I': '�', 'J': '�', 'K': '�',
           'L': '�', 'M': '�', 'N': '�',
           'O': '�', 'P': '�', 'Q': '�',
           'R': '�', 'S': '�', 'T': '�',
           'U': '�', 'V': '�', 'W': '�',
           'X': '�', 'Y': '�', 'Z': '�'}

def readcstr(f):
    buf = bytearray()
    while True:
        b = f.read(1)
        if b is None or b == '\0' or not b:
            return str(buf)
        else:
            buf.append(charMap[b] if b in charMap else b)

try:
    os.makedirs('temps')
except OSError as e:
    if e.errno != errno.EEXIST:
        raise
try:
    os.makedirs('texts')
except OSError as e:
    if e.errno != errno.EEXIST:
        raise

with open('SIMON.GME', 'rb') as gmeFile:
    offsets = []
    offsets.append(struct.unpack('<I', gmeFile.read(4))[0])
    while gmeFile.tell() < offsets[0]:
        offsets.append(struct.unpack('<I', gmeFile.read(4))[0])

    for idx, offset in enumerate(offsets[:-1]):
        with open('temps/tempfile{:04}.bin'.format(idx), 'wb') as tempFile:
            tempFile.write(gmeFile.read(offsets[idx + 1] - offset))

    with open('temps/tempfile{:04}.bin'.format(len(offsets)), 'wb') as tempFile:
            tempFile.write(gmeFile.read())

textFiles = []
with open('STRIPPED.TXT', 'rb') as strpFile:
    while True:
        name = strpFile.read(7)
        if not name:
            break
        unknown = struct.unpack('<I', strpFile.read(1) + '\x00\x00\x00')[0]
        offsetProbably = struct.unpack('<I', strpFile.read(1) + '\x00\x00\x00')[0]
        textFiles.append(name)


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
            strr = readcstr(tempFile)
            if not strr:
                break
            strFile.write(str(strr + '\r\n'))

        

