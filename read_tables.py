import os
from collections import deque

from chiper import decrypt, hebrew_char_map
from gamepc import read_gamepc
from gmepack import index_table_files, index_text_files
from gamepc_script import load_tables
from opcode import simon_ops_talkie


if __name__ == '__main__':
    text_files = list(index_text_files('STRIPPED.TXT'))
    tables = list(index_table_files('TBLLIST'))

    all_strings = {}

    with open('strings.txt', 'w', encoding='windows-1255') as str_file:
        with open('GAMEPC', 'rb') as game_file:
            _, _, _, texts, _ = read_gamepc(game_file)
            assert game_file.read() == b''
        strings = dict(enumerate(decrypt(msg, hebrew_char_map, 'windows-1255') for msg in texts))
        all_strings.update(strings)


        for idx, line in strings.items():
            print('GAMEPC', idx, line, sep='\t', file=str_file)

        base_min = 0x8000
        base_q = deque()
        for fname, base_max in text_files:
            base_q.append(base_max)
            with open(os.path.join('temps', fname), 'rb') as text_file:
            # with open(fname, 'rb') as text_file:
                texts = text_file.read().split(b'\0')[:-1]
            strings = dict(enumerate((decrypt(msg, hebrew_char_map, 'windows-1255') for msg in texts), start=base_min))
            all_strings.update(strings)
            if strings:
                base_min = base_q.popleft()

            for idx, line in strings.items():
                print(fname, idx, line, sep='\t', file=str_file)

    with open('script_dump.txt', 'w', encoding='utf-8') as scr_file: 
        for fname, subs in tables:
            print(fname, subs, file=scr_file)
            with open(os.path.join('temps', fname), 'rb') as tbl_file:
            # with open(fname, 'rb') as tbl_file:
                for sub in subs:
                    print('SUBROUTINE', sub, file=scr_file)
                    for i in range(sub[0], sub[1] + 1):
                        for t in load_tables(tbl_file, all_strings, simon_ops_talkie):
                            print(t, file=scr_file)
