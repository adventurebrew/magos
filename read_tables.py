import io
import os
from collections import deque

from chiper import decrypt, hebrew_char_map, identity_map
from gamepc import read_gamepc
from gmepack import index_table_files, index_text_files
from gamepc_script import load_tables, read_object
from opcode import simon_ops_talkie, simon_ops


if __name__ == '__main__':
    text_files = list(index_text_files('STRIPPED.TXT'))
    tables = list(index_table_files('TBLLIST'))

    all_strings = {}

    with open('strings.txt', 'w', encoding='windows-1255') as str_file, \
            open('script_dump.txt', 'w', encoding='utf-8') as scr_file:
        with open('GAMEPC', 'rb') as game_file:
            total_item_count, version, item_count, texts, tables_data = read_gamepc(game_file)
            assert game_file.read() == b''

        strings = dict(enumerate(decrypt(msg, hebrew_char_map, 'windows-1255') for msg in texts))
        all_strings.update(strings)

        for idx, line in strings.items():
            print('GAMEPC', idx, line, sep='\t', file=str_file)

        with io.BytesIO(tables_data) as stream:
            # objects[1] is the player
            null = {'children': []}
            player = {'children': []}
            objects = [null, player] + [read_object(stream, all_strings) for i in range(2, item_count)]

            for item in objects:
                print(item)

            for t in load_tables(stream, all_strings, simon_ops_talkie):
                print(t, file=scr_file)


        base_min = 0x8000
        base_q = deque()
        for fname, base_max in text_files:
            base_q.append(base_max)
            with open(os.path.join('temps', fname), 'rb') as text_file:
            # with open(fname, 'rb') as text_file:
                texts = text_file.read().split(b'\0')
            last_text = texts.pop()
            assert last_text == b''
            strings = dict(enumerate((decrypt(msg, hebrew_char_map, 'windows-1255') for msg in texts), start=base_min))
            all_strings.update(strings)
            if strings:
                base_min = base_q.popleft()

            for idx, line in strings.items():
                print(fname, idx, line, sep='\t', file=str_file)

        for fname, subs in tables:
            # print(fname, subs, file=scr_file)
            with open(os.path.join('temps', fname), 'rb') as tbl_file:
            # with open(fname, 'rb') as tbl_file:
                for sub in subs:
                    print('SUBROUTINE', sub, file=scr_file)
                    for i in range(sub[0], sub[1] + 1):
                        for t in load_tables(tbl_file, all_strings, simon_ops_talkie):
                            print(t, file=scr_file)
