simon_ops = dict(
    enumerate(
        (
            ('NOT', ' '),
            ('AT', 'I '),
            ('NOTAT', 'I '),
            ('PRESENT', 'I '),
            ('ABSENT','I '),
            ('CARRIED', 'I '),
            ('NOTCARR', 'I '),
            ('ISAT', 'II '),
            ('ISNOTAT', 'II '),
            ('ISBY', 'II '),
            ('ISNOTBY', 'II '),
            ('ZERO', 'B '),
            ('NOTZERO', 'B '),
            ('EQ', 'BN '),
            ('NOTEQ', 'BN '),
            ('GT', 'BN '),
            ('LT', 'BN '),
            ('EQF', 'BB '),
            ('NOTEQF','BB '),
            ('LTF', 'BB '),
            ('GTF', 'BB '),
            ('ISIN', 'II '),
            ('ISNOTIN', 'II '),
            ('CHANCE', 'N '),
            ('ISPLAYER', 'I '),
            ('ISROOM','I '),
            ('ISOBJECT', 'I '),
            ('STATE', 'IN '),
            ('OFLAG', 'IB '),
            ('CANPUT','II '),
            ('CREATE','I '),
            ('DESTROY', 'I '),
            ('SWAP', 'II '),
            ('PLACE', 'II '),
            ('COPYOF', 'IBB '),
            ('COPYFO', 'BIB '),
            ('COPYFF', 'BB '),
            ('WHATO', 'B '),
            ('GETO', 'BI '),
            ('WEIGH', 'IB '),
            ('SET', 'B '),
            ('CLEAR', 'B '),
            ('LET', 'BN '),
            ('ADD', 'BN '),
            ('SUB', 'BN '),
            ('ADDF', 'BB '),
            ('SUBF', 'BB '),
            ('MUL', 'BN '),
            ('DIV', 'BN '),
            ('MULF', 'BB '),
            ('DIVF', 'BB '),
            ('MOD', 'BN '),
            ('MODF', 'BB '),
            ('RANDOM','BN '),
            ('MOVE', 'B '),
            ('GOTO', 'I '),
            ('OSET', 'IB '),
            ('OCLEAR','IB '),
            ('PUTBY', 'II '),
            ('INC', 'I '),
            ('DEC', 'I '),
            ('SETSTATE', 'IN '),
            ('PRINT', 'B '),
            ('MESSAGE', 'T '),
            ('MSG', 'T '),
            ('ADD_TEXT_BOX', 'NNNNNB '),
            ('SET_SHORT_TEXT', 'BT '),
            ('SET_LONG_TEXT', 'BT '),
            ('END', 'T '),
            ('DONE', ' '),
            ('SHOW_STRING_AR3', 'B '),
            ('PROCESS', 'N '),
            ('DOCLASS', 'IBN '),
            ('POBJ', 'I '),
            ('PNAME', 'I '),
            ('PCNAME', 'I '),
            ('WHEN', 'NN '),
            ('IF1', ' '),
            ('IF2', ' '),
            ('ISCALLED', 'IT '),
            ('IS', 'II '),
            ('EXITS', 'I '),
            ('DEBUG', 'B '),
            ('RESCAN',' '),
            ('CANGOBY', 'IB '),
            ('WHERETO', 'IBB '),
            ('DOOREXIT', 'IIB '),
            ('COMMENT', 'T '),
            ('STOP_ANIMATION', ' '),
            ('RESTART_ANIMATION', ' '),
            ('GETPARENT', 'IB '),
            ('GETNEXT', 'IB '),
            ('GETCHILDREN', 'IB '),
            ('PEXIT', 'B '),
            ('FINDMASTER', 'BB '),
            ('NEXTMASTER', 'IBB '),
            ('PICTURE', 'NB '),
            ('LOAD_ZONE', 'N '),
            ('ANIMATE', 'NBNNN '),
            ('STOP_ANIMATE', 'N '),
            ('KILL_ANIMATE', ' '),
            ('DEFINE_WINDOW', 'BNNNNNN '),
            ('CHANGE_WINDOW','B '),
            ('CLS', ' '),
            ('CLOSE_WINDOW', 'B '),
            ('MENU', 'B '),
            ('TEXT_MENU', 'BB '),
            ('ADD_BOX', 'NNNNNIN '),
            ('DEL_BOX','N '),
            ('ENABLE_BOX', 'N '),
            ('DISABLE_BOX', 'N '),
            ('MOVE_BOX', 'NNN '),
            ('DRAW_ICON', 'NBNN '),
            ('DRAW_ITEM', 'IBNN '),
            ('DO_ICONS', 'IB '),
            ('ISCLASS', 'IB '),
            ('SETCLASS', 'IB '),
            ('UNSETCLASS', 'IB '),
            ('WAIT', 'N '),
            ('WAIT_SYNC', 'N '),
            ('SYNC', 'N '),
            ('DEF_OBJ','BI '),
            ('ENABLE_INPUT', ' '),
            ('SET_TIME', ' '),
            ('IF_TIME','N '),
            ('IS_SIBLING_WITH_A', 'I '),
            ('DO_CLASS_ICONS', 'IBB '),
            ('PLAY_TUNE', 'NN '),
            ('WAITENDTUNE', 'N '),
            ('IFENDTUNE', 'N '),
            ('SET_ADJ_NOUN', 'Ban '),
            ('ZONEDISK', 'BB '),
            ('SAVE_USER_GAME', ' '),
            ('LOAD_USER_GAME', ' '),
            ('STOP_TUNE', ' '),
            ('PAUSE', ' '),
            ('COPY_SF', 'IB '),
            ('RESTORE_ICONS', 'B '),
            ('FREEZE_ZONES', ' '),
            ('SET_PARENT_SPECIAL', 'II '),
            ('CLEAR_TIMERS', ' '),
            ('SET_M1_OR_M3', 'BI '),
            ('IS_BOX', 'N '),
            ('START_ITEM_SUB', 'I '),
            (None, 'IB '),
            (None, 'IB '),
            (None, 'IB '),
            (None, 'IB '),
            (None, 'IB '),
            (None, 'IB '),
            (None, 'IB '),
            ('STORE_ITEM', 'BI '),
            ('GET_ITEM', 'BB '),
            ('SET_BIT', 'B '),
            ('CLEAR_BIT', 'B '),
            ('IS_BIT_CLEAR', 'B '),
            ('IS_BIT_SET', 'B '),
            ('GET_ITEM_PROP', 'IBB '),
            ('SET_ITEM_PROP', 'IBN '),
            (None, 'IB '),
            ('SET_INK', 'B '),
            ('SETUP_TEXT', 'BNBN '),
            ('PRINT_STR', 'BBT '),
            ('PLAY_EFFECT', 'N '),
            ('getDollar2', ' '),
            ('IS_ADJ_NOUN', 'Ian '),
            ('SET_BIT2', 'B '),
            ('CLEAR_BIT2', 'B '),
            ('IS_BIT2_CLEAR', 'B '),
            ('IS_BIT2_SET', 'B '),
            (None, 'T '),
            (None, 'T '),
            (None, 'B '),
            (None, ' '),
            (None, 'I '),
            ('LOCK_ZONES', ' '),
            ('UNLOCK_ZONES', ' '),
            ('SCREEN_TEXT_POBJ', 'BBI '),
            ('GETPATHPOSN', 'NNBB '),
            ('SCREEN_TEXT_LONG_TEXT', 'BBB '),
            ('MOUSE_ON', ' '),
            ('MOUSE_OFF', ' '),
            ('LOAD_BEARD', ' '),
            ('UNLOAD_BEARD', ' '),
            ('UNLOAD_ZONE', 'N '),
            ('LOAD_SOUND_FILES', 'N '),
            ('UNFREEZE_ZONES', ' '),
            ('FADE_TO_BLACK', ' '),
        )
    )
)


simon_ops_talkie = {
    **simon_ops,
    0x43: ('SET_LONG_TEXT', 'BTS '),
    0xa2: ('PRINT_STR', 'BBTS ')
}


simon2_ops = {
    **simon_ops,
    0x62: ('ANIMATE', 'NNBNNN '),
    0x63: ('STOP_ANIMATE', 'NN '),
    0x7f: ('PLAY_TUNE', 'NNB '),
    0xbc: ('STRING2_IS', 'BT '),
    0xbd: ('CLEAR_MARKS', ' '),
    0xbe: ('WAIT_FOR_MARK', 'B '),
}


simon2_ops_talkie = {
    **simon2_ops,
    0x43: ('SET_LONG_TEXT', 'BTS '),
    0xa2: ('PRINT_STR', 'BBTS ')
}