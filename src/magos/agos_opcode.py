from collections.abc import Mapping

OpTable = Mapping[int, tuple[str | None, str]]

simon_ops: OpTable = {
    0x00: ('NOT', ' '),
    0x01: ('AT', 'I '),
    0x02: ('NOTAT', 'I '),
    0x03: ('PRESENT', 'I '),
    0x04: ('ABSENT', 'I '),
    0x05: ('CARRIED', 'I '),
    0x06: ('NOTCARR', 'I '),
    0x07: ('ISAT', 'II '),
    0x08: ('ISNOTAT', 'II '),
    0x09: ('ISBY', 'II '),
    0x0A: ('ISNOTBY', 'II '),
    0x0B: ('ZERO', 'B '),
    0x0C: ('NOTZERO', 'B '),
    0x0D: ('EQ', 'BN '),
    0x0E: ('NOTEQ', 'BN '),
    0x0F: ('GT', 'BN '),
    0x10: ('LT', 'BN '),
    0x11: ('EQF', 'BB '),
    0x12: ('NOTEQF', 'BB '),
    0x13: ('LTF', 'BB '),
    0x14: ('GTF', 'BB '),
    0x15: ('ISIN', 'II '),
    0x16: ('ISNOTIN', 'II '),
    0x17: ('CHANCE', 'N '),
    0x18: ('ISPLAYER', 'I '),
    0x19: ('ISROOM', 'I '),
    0x1A: ('ISOBJECT', 'I '),
    0x1B: ('STATE', 'IN '),
    0x1C: ('OFLAG', 'IB '),
    0x1D: ('CANPUT', 'II '),
    0x1E: ('CREATE', 'I '),
    0x1F: ('DESTROY', 'I '),
    0x20: ('SWAP', 'II '),
    0x21: ('PLACE', 'II '),
    0x22: ('COPYOF', 'IBB '),
    0x23: ('COPYFO', 'BIB '),
    0x24: ('COPYFF', 'BB '),
    0x25: ('WHATO', 'B '),
    0x26: ('GETO', 'BI '),
    0x27: ('WEIGH', 'IB '),
    0x28: ('SET', 'B '),
    0x29: ('CLEAR', 'B '),
    0x2A: ('LET', 'BN '),
    0x2B: ('ADD', 'BN '),
    0x2C: ('SUB', 'BN '),
    0x2D: ('ADDF', 'BB '),
    0x2E: ('SUBF', 'BB '),
    0x2F: ('MUL', 'BN '),
    0x30: ('DIV', 'BN '),
    0x31: ('MULF', 'BB '),
    0x32: ('DIVF', 'BB '),
    0x33: ('MOD', 'BN '),
    0x34: ('MODF', 'BB '),
    0x35: ('RANDOM', 'BN '),
    0x36: ('MOVE', 'B '),
    0x37: ('GOTO', 'I '),
    0x38: ('OSET', 'IB '),
    0x39: ('OCLEAR', 'IB '),
    0x3A: ('PUTBY', 'II '),
    0x3B: ('INC', 'I '),
    0x3C: ('DEC', 'I '),
    0x3D: ('SETSTATE', 'IN '),
    0x3E: ('PRINT', 'B '),
    0x3F: ('MESSAGE', 'T '),
    0x40: ('MSG', 'T '),
    0x41: ('ADD_TEXT_BOX', 'NNNNNB '),
    0x42: ('SET_SHORT_TEXT', 'BT '),
    0x43: ('SET_LONG_TEXT', 'BT '),
    0x44: ('END', 'T '),
    0x45: ('DONE', ' '),
    0x46: ('SHOW_STRING_AR3', 'B '),
    0x47: ('PROCESS', 'N '),
    0x48: ('DOCLASS', 'IBN '),
    0x49: ('POBJ', 'I '),
    0x4A: ('PNAME', 'I '),
    0x4B: ('PCNAME', 'I '),
    0x4C: ('WHEN', 'NN '),
    0x4D: ('IF1', ' '),
    0x4E: ('IF2', ' '),
    0x4F: ('ISCALLED', 'IT '),
    0x50: ('IS', 'II '),
    0x51: ('EXITS', 'I '),
    0x52: ('DEBUG', 'B '),
    0x53: ('RESCAN', ' '),
    0x54: ('CANGOBY', 'IB '),
    0x55: ('WHERETO', 'IBB '),
    0x56: ('DOOREXIT', 'IIB '),
    0x57: ('COMMENT', 'T '),
    0x58: ('STOP_ANIMATION', ' '),
    0x59: ('RESTART_ANIMATION', ' '),
    0x5A: ('GETPARENT', 'IB '),
    0x5B: ('GETNEXT', 'IB '),
    0x5C: ('GETCHILDREN', 'IB '),
    0x5D: ('PEXIT', 'B '),
    0x5E: ('FINDMASTER', 'BB '),
    0x5F: ('NEXTMASTER', 'IBB '),
    0x60: ('PICTURE', 'NB '),
    0x61: ('LOAD_ZONE', 'N '),
    0x62: ('ANIMATE', 'NBNNN '),
    0x63: ('STOP_ANIMATE', 'N '),
    0x64: ('KILL_ANIMATE', ' '),
    0x65: ('DEFINE_WINDOW', 'BNNNNNN '),
    0x66: ('CHANGE_WINDOW', 'B '),
    0x67: ('CLS', ' '),
    0x68: ('CLOSE_WINDOW', 'B '),
    0x69: ('MENU', 'B '),
    0x6A: ('TEXT_MENU', 'BB '),
    0x6B: ('ADD_BOX', 'NNNNNIN '),
    0x6C: ('DEL_BOX', 'N '),
    0x6D: ('ENABLE_BOX', 'N '),
    0x6E: ('DISABLE_BOX', 'N '),
    0x6F: ('MOVE_BOX', 'NNN '),
    0x70: ('DRAW_ICON', 'NBNN '),
    0x71: ('DRAW_ITEM', 'IBNN '),
    0x72: ('DO_ICONS', 'IB '),
    0x73: ('ISCLASS', 'IB '),
    0x74: ('SETCLASS', 'IB '),
    0x75: ('UNSETCLASS', 'IB '),
    0x76: ('WAIT', 'N '),
    0x77: ('WAIT_SYNC', 'N '),
    0x78: ('SYNC', 'N '),
    0x79: ('DEF_OBJ', 'BI '),
    0x7A: ('ENABLE_INPUT', ' '),
    0x7B: ('SET_TIME', ' '),
    0x7C: ('IF_TIME', 'N '),
    0x7D: ('IS_SIBLING_WITH_A', 'I '),
    0x7E: ('DO_CLASS_ICONS', 'IBB '),
    0x7F: ('PLAY_TUNE', 'NN '),
    0x80: ('WAITENDTUNE', 'N '),
    0x81: ('IFENDTUNE', 'N '),
    0x82: ('SET_ADJ_NOUN', 'Ban '),
    0x83: ('ZONEDISK', 'BB '),
    0x84: ('SAVE_USER_GAME', ' '),
    0x85: ('LOAD_USER_GAME', ' '),
    0x86: ('STOP_TUNE', ' '),
    0x87: ('PAUSE', ' '),
    0x88: ('COPY_SF', 'IB '),
    0x89: ('RESTORE_ICONS', 'B '),
    0x8A: ('FREEZE_ZONES', ' '),
    0x8B: ('SET_PARENT_SPECIAL', 'II '),
    0x8C: ('CLEAR_TIMERS', ' '),
    0x8D: ('SET_M1_OR_M3', 'BI '),
    0x8E: ('IS_BOX', 'N '),
    0x8F: ('START_ITEM_SUB', 'I '),
    0x90: (None, 'IB '),
    0x91: (None, 'IB '),
    0x92: (None, 'IB '),
    0x93: (None, 'IB '),
    0x94: (None, 'IB '),
    0x95: (None, 'IB '),
    0x96: (None, 'IB '),
    0x97: ('STORE_ITEM', 'BI '),
    0x98: ('GET_ITEM', 'BB '),
    0x99: ('SET_BIT', 'B '),
    0x9A: ('CLEAR_BIT', 'B '),
    0x9B: ('IS_BIT_CLEAR', 'B '),
    0x9C: ('IS_BIT_SET', 'B '),
    0x9D: ('GET_ITEM_PROP', 'IBB '),
    0x9E: ('SET_ITEM_PROP', 'IBN '),
    0x9F: (None, 'IB '),
    0xA0: ('SET_INK', 'B '),
    0xA1: ('SETUP_TEXT', 'BNBN '),
    0xA2: ('PRINT_STR', 'BBT '),
    0xA3: ('PLAY_EFFECT', 'N '),
    0xA4: ('getDollar2', ' '),
    0xA5: ('IS_ADJ_NOUN', 'Ian '),
    0xA6: ('SET_BIT2', 'B '),
    0xA7: ('CLEAR_BIT2', 'B '),
    0xA8: ('IS_BIT2_CLEAR', 'B '),
    0xA9: ('IS_BIT2_SET', 'B '),
    0xAA: (None, 'T '),
    0xAB: (None, 'T '),
    0xAC: (None, 'B '),
    0xAD: (None, ' '),
    0xAE: (None, 'I '),
    0xAF: ('LOCK_ZONES', ' '),
    0xB0: ('UNLOCK_ZONES', ' '),
    0xB1: ('SCREEN_TEXT_POBJ', 'BBI '),
    0xB2: ('GETPATHPOSN', 'NNBB '),
    0xB3: ('SCREEN_TEXT_LONG_TEXT', 'BBB '),
    0xB4: ('MOUSE_ON', ' '),
    0xB5: ('MOUSE_OFF', ' '),
    0xB6: ('LOAD_BEARD', ' '),
    0xB7: ('UNLOAD_BEARD', ' '),
    0xB8: ('UNLOAD_ZONE', 'N '),
    0xB9: ('LOAD_SOUND_FILES', 'N '),
    0xBA: ('UNFREEZE_ZONES', ' '),
    0xBB: ('FADE_TO_BLACK', ' '),
}


simon_ops_talkie: OpTable = {
    **simon_ops,
    0x43: ('SET_LONG_TEXT', 'BTS '),
    0xA2: ('PRINT_STR', 'BBTS '),
}


waxworks_ops: OpTable = {
    **simon_ops,
    0x58: (None, 'T '),
    0x59: ('LOAD_GAME', 'T '),
    0x90: ('SET_DOOR_OPEN', 'IB '),
    0x91: ('SET_DOOR_CLOSED', 'IB '),
    0x92: ('SET_DOOR_LOCKED', 'IB '),
    0x93: ('SET_DOOR_UNLOCKED', 'IB '),
    0x94: ('IF_DOOR_OPEN', 'IB '),
    0x95: ('IF_DOOR_CLOSED', 'IB '),
    0x96: ('IF_DOOR_LOCKED', 'IB '),
    0xA1: (None, ' '),
    0xA2: (None, 'TB '),
    0xA3: (None, 'TB '),
    0xA4: (None, 'I '),
    0xA5: (None, 'N '),
    0xA6: (None, 'B '),
    0xA7: (None, 'INB '),
    0xA8: (None, 'INB '),
    0xA9: (None, 'INB '),
    0xAA: (None, 'INB '),
    0xAB: (None, 'INB '),
    0xAC: (None, 'INB '),
    0xAD: (None, 'INB '),
    0xAE: (None, 'N '),
    0xAF: ('getDollar2', ' '),
    0xB0: (None, 'INBB '),
    0xB1: (None, 'B '),
    0xB2: (None, 'B '),
    0xB3: ('IS_ADJ_NOUN', 'Ian '),
    0xB4: ('SET_BIT2', 'B '),
    0xB5: ('CLEAR_BIT2', 'B '),
    0xB6: ('IS_BIT2_CLEAR', 'B '),
    0xB7: ('IS_BIT2_SET', 'B '),
    0xB8: ('BOX_MESSAGE', 'T '),
    0xB9: ('BOX_MSG', 'T '),
    0xBA: ('BOX_LONG_TEXT', 'B '),
    0xBB: ('PRINT_BOX', ' '),
    0xBC: ('BOX_POBJ', 'I '),
    0xBD: ('LOCK_ZONES', ' '),
    0xBE: ('UNLOCK_ZONES', ' '),
}


simon2_ops: OpTable = {
    **simon_ops,
    0x62: ('ANIMATE', 'NNBNNN '),
    0x63: ('STOP_ANIMATE', 'NN '),
    0x7F: ('PLAY_TUNE', 'NNB '),
    0xBC: ('STRING2_IS', 'BT '),
    0xBD: ('CLEAR_MARKS', ' '),
    0xBE: ('WAIT_FOR_MARK', 'B '),
}


simon2_ops_talkie: OpTable = {
    **simon2_ops,
    0x43: ('SET_LONG_TEXT', 'BTS '),
    0xA2: ('PRINT_STR', 'BBTS '),
}


feeble_ops: OpTable = {
    **simon2_ops_talkie,
    0x7A: ('ORACLE_TEXT_DOWN', ' '),
    0x7B: ('ORACLE_TEXT_UP', ' '),
    0x83: ('SET_TIME', ' '),
    0x86: ('LIST_SAVED_GAMES', ' '),
    0x87: ('SWITCH_CD', ' '),
    0xA1: ('SETUP_TEXT', 'BNNN '),
    0xAB: ('HYPERLINK_ON', 'N '),
    0xAC: ('HYPERLINK_OFF', ' '),
    0xAD: ('CHECK_PATHS', ' '),
    0xB6: ('LOAD_VIDEO', 'T '),
    0xB7: ('PLAY_VIDEO', ' '),
    0xBB: ('CENTER_SCROLL', ' '),
    0xBF: ('RESET_PV_COUNT', ' '),
    0xC0: ('SET_PATH_VALUES', 'BBBB '),
    0xC1: ('STOP_CLOCK', ' '),
    0xC2: ('RESTART_CLOCK', ' '),
    0xC3: ('SET_COLOR', 'BBBB '),
    0xC4: ('B3_SET', 'B '),
    0xC5: ('B3_CLEAR', 'B '),
    0xC6: ('B3_ZERO', 'B '),
    0xC7: ('B3_NOT_ZERO', 'B '),
}
