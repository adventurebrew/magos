import os

from chiper import identity_map
from stream import write_uint32be


def create_directory(name):
    os.makedirs(name, exist_ok=True)


def make_texts(map_char, encoding: str = 'windows-1255'):
    create_directory('texts-gamepc')

    with open('GAMEPC-NEW', 'wb') as game_file, open('texts-gamepc/THEREST', 'rb') as rest_file:
        game_file.write(rest_file.read(12))
        with open('texts-gamepc/gamepc.txt', 'r', encoding=encoding) as text_file:
            lines = [line.split('\t', maxsplit=1)[1].rstrip('\n') for line in text_file]
            content = b'\0'.join(map_char(line.encode(encoding)) for line in lines) + b'\0'
        game_file.write(write_uint32be(len(lines)) + write_uint32be(len(content)) + content)
        game_file.write(rest_file.read())


if __name__ == '__main__':
    make_texts(identity_map)
