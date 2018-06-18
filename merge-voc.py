import struct

vocFile = open('SIMON2.VOC', 'rb')
datFile = open('TEMP_DAT', 'wb')
idxFile = open('TEMP_IDX', 'wb')
offsets = []
ext = 'voc'

def get_sound(num):
    name = 'tempfile{:04}.{}'.format(num, ext)
    size = 0
    with open(ext + '/' + name.format(num), 'rb') as tempFile:
        datFile.write(tempFile.read())
        size= tempFile.tell()
    return size

def get_offsets(maxcount):
    for i in range(maxcount):
        buf = vocFile.read(8)
        if buf == 'Creative' or buf[:4] == 'RIFF':
            return i
        vocFile.seek(-8, 1)
        offsets.append(struct.unpack('<I', vocFile.read(4)))

num = get_offsets(32768)
offsets.append(0)
size = num * 4
idxFile.write(struct.pack('<I', 0))
idxFile.write(struct.pack('<I', size))

j = 0
for i in range(1, num):
    if offsets[i] == offsets[i + 1]:
        idxFile.write(struct.pack('<I', size))
        continue

    if offsets[i] != 0:
        size += get_sound(j)
    if i < num - 1:
        idxFile.write(struct.pack('<I', size))
        j += 1

vocFile.close()
datFile.close()
idxFile.close()

datFile = open('TEMP_DAT', 'rb')
idxFile = open('TEMP_IDX', 'rb')
output = open('simon2-new.{}'.format(ext), 'wb')
output.write(idxFile.read())
output.write(datFile.read())
output.close()
datFile.close()
idxFile.close()
