from chiper import decrypt, hebrew_char_map, identity_map
from stream import create_directory, read_uint32be, write_uint32be
from gamepc import read_gamepc


def make_texts(map_char, encoding='windows-1255'):
    create_directory('texts-gamepc')

    with open('GAMEPC', 'rb') as game_file:
        total_item_count, version, item_count, texts, tables = read_gamepc(game_file)
        assert game_file.read() == b''
    strings = [decrypt(msg, map_char, encoding) for msg in texts]
    with open('texts-gamepc/gamepc.txt', 'w', encoding=encoding) as str_file:
        for idx, msg in enumerate(strings):
            assert '\t' not in msg
            assert '\n' not in msg
            print(idx, msg, file=str_file, sep='\t')

    with open('texts-gamepc/THEREST', 'wb') as f:
        f.write(write_uint32be(total_item_count - 2))
        f.write(write_uint32be(version))
        f.write(write_uint32be(item_count - 2))
        f.write(tables)


if __name__ == '__main__':
    import sys
    map_char = identity_map
    if len(sys.argv) > 2:
        try:
            if sys.argv[1] in ('--decrypt', '-d'):
                if sys.argv[2] == 'he':
                    map_char = hebrew_char_map
                else:
                    raise IndexError
        except IndexError as e:
            print('Usage:\n' + 'python split-gme.py [--decrypt he] SIMON.GME')
            exit(1)

    make_texts(map_char)
