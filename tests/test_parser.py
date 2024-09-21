import pytest

from magos.gamepc_script import (
    BASE_MIN,
    ArgumentParseError,
    Command,
    InvalidTextReferenceError,
    OpcodeCommandMismatchError,
    Param,
    ParameterCountMismatchError,
    Parser,
    UnrecognizedCommandError,
    parse_cmds,
)


@pytest.fixture
def parser() -> Parser:
    return Parser(
        {
            0x00: ('VC_EMPTY', ' '),
            0x01: ('VC_I', 'I '),
            0x02: ('VC_IB', 'IB '),
            0x03: ('VC_NT', 'NT '),
        },
    )


@pytest.mark.parametrize(
    'script',
    [
        """
        VC_EMPTY
        VC_I 7
        VC_IB 2 3
        VC_NT 10 12
        """,
        'VC_EMPTY VC_I 7 VC_IB 2 3 VC_NT 10 12',
        """
        (0x00) VC_EMPTY
        VC_I 7
        VC_IB 2 3 (0x03) VC_NT 10 12
        """,
        """
        (0x00) VC_EMPTY
        (0x01) VC_I 7
        (0x02)
        VC_IB 2
        3

        (0x03) VC_NT 10 12
        """,
    ],
    ids=['newline', 'space', 'mixed_with_some_opcodes', 'mixed_with_newlines'],
)
def test_valid_cmds(parser: Parser, script: str) -> None:
    """
    Given a script with valid commands in various formats,
    When the script is parsed,
    Then the parser should correctly parse the commands.

    Test cases include:
    - Commands separated by newlines.
    - Commands separated by spaces.
    - Commands with mixed formats and some optional opcodes.
    - Commands with mixed formats and newlines.
    """
    text_range = range(BASE_MIN, BASE_MIN + 100)
    expected_output = [
        Command(0x00, 'VC_EMPTY', ()),
        Command(0x01, 'VC_I', (Param('I', '7'),)),
        Command(0x02, 'VC_IB', (Param('I', '2'), Param('B', 3))),
        Command(0x03, 'VC_NT', (Param('N', 10), Param('T', 12))),
    ]
    assert list(parse_cmds(script.split(), parser, text_range)) == expected_output


def test_opcode_mismatch(parser: Parser) -> None:
    """
    Given a command with an incorrect opcode,
    When the command is parsed,
    Then the parser should raise an `OpcodeCommandMismatchError` and provide a detailed
    error message highlighting the command with the incorrect opcode.
    """
    script = """
        (0x01) VC_EMPTY
        VC_I 7
        VC_IB 2 3
        (0x03) VC_NT 10 12
    """
    text_range = range(BASE_MIN, BASE_MIN + 100)
    with pytest.raises(OpcodeCommandMismatchError) as excinfo:
        list(parse_cmds(script.split(), parser, text_range))
    assert (
        excinfo.value.args[0]
        == 'opcode for VC_EMPTY should have been (0x00) but found (0x01)'
    )
    assert '-> (0x01) VC_EMPTY <-' in excinfo.value.highlight(script)


def test_invalid_cmd(parser: Parser) -> None:
    """
    Given an unrecognized command,
    When the command is parsed,
    Then the parser should raise an `UnrecognizedCommandError` and provide a detailed
    error message highlighting the unrecognized command.
    """
    script = """
        INVC_EMPTY
        VC_I 7
    """
    text_range = range(BASE_MIN, BASE_MIN + 100)
    with pytest.raises(UnrecognizedCommandError) as excinfo:
        list(parse_cmds(script.split(), parser, text_range))
    assert excinfo.value.args[0] == 'unrecognized command name INVC_EMPTY'
    assert '-> INVC_EMPTY <-' in excinfo.value.highlight(script)


def test_invalid_arg(parser: Parser) -> None:
    """
    Given a command with an invalid argument,
    When the command is parsed,
    Then the parser should raise an `ArgumentParseError` and provide a detailed
    error message highlighting the command with the invalid argument.
    """
    script = """
        VC_I 7
        VC_IB 2 string
        VC_NT 10 12
    """
    text_range = range(BASE_MIN, BASE_MIN + 100)
    with pytest.raises(ArgumentParseError) as excinfo:
        list(parse_cmds(script.split(), parser, text_range))
    assert excinfo.value.args[0].startswith(
        'could not parse given arguments 2 string as types IB',
    )
    assert '-> VC_IB 2 string <-' in excinfo.value.highlight(script)


@pytest.mark.parametrize(
    'args',
    [
        '2',
        '2 3 4',
    ],
    ids=['fewer_args', 'extra_args'],
)
def test_invalid_arg_count(parser: Parser, args: str) -> None:
    """
    Given a command with an incorrect number of parameters,
    When the command is parsed,
    Then the parser should raise a `ParameterCountMismatchError` and provide a detailed
    error message highlighting the command with the incorrect number of parameters.

    Test cases include:
    - Command with fewer parameters (1) than expected (2).
    - Command with more parameters (3) than expected (2).
    """
    script = f"""
        VC_I 7
        VC_IB {args}
        VC_NT 10 12
    """
    text_range = range(BASE_MIN, BASE_MIN + 100)
    with pytest.raises(ParameterCountMismatchError) as excinfo:
        list(parse_cmds(script.split(), parser, text_range))
    num_args = len(args.split())
    assert (
        excinfo.value.args[0]
        == f'VC_IB expects 2 parameters of types IB but {num_args} given: {args}'
    )
    assert f'-> VC_IB {args} <-' in excinfo.value.highlight(script)


@pytest.mark.parametrize(
    ('text_num', 'range_min', 'range_max'),
    [
        (BASE_MIN + 50, BASE_MIN + 100, BASE_MIN + 200),
        (BASE_MIN + 100, BASE_MIN + 50, BASE_MIN + 100),
        (BASE_MIN + 100, BASE_MIN, BASE_MIN + 50),
    ],
    ids=['below_loaded_range', 'just_above_loaded_range', 'above_loaded_range'],
)
def test_invalid_text_ref(
    parser: Parser,
    text_num: int,
    range_min: int,
    range_max: int,
) -> None:
    """
    Given a command with an invalid text reference,
    When the command is parsed,
    Then the parser should raise an `InvalidTextReferenceError` and provide a detailed
    error message highlighting the invalid text reference.

    Test cases include:
    - Text reference below the loaded text range.
    - Text reference just above the upper bound of the loaded text range.
    - Text reference above the loaded text range.
    """
    script = f"""
        VC_I 7
        VC_IB 2 3
        VC_NT 10 {text_num}
        VC_NT 10 12
    """
    text_range = range(range_min, range_max)
    with pytest.raises(InvalidTextReferenceError) as excinfo:
        list(parse_cmds(script.split(), parser, text_range))
    assert excinfo.value.args[0].startswith(
        f'text {text_num} is outside of expected range for current file',
    )
    assert f'VC_NT 10 -> {text_num} <-' in excinfo.value.highlight(script)


@pytest.mark.parametrize(
    ('text_num', 'range_min', 'range_max'),
    [
        (50, BASE_MIN + 100, BASE_MIN + 200),
        (BASE_MIN + 100, BASE_MIN + 50, BASE_MIN + 200),
        (BASE_MIN + 100, BASE_MIN + 100, BASE_MIN + 101),
    ],
    ids=['global_range', 'loaded_range', 'loaded_range_lower_bound'],
)
def test_valid_text_ref(
    parser: Parser,
    text_num: int,
    range_min: int,
    range_max: int,
) -> None:
    """
    Given a command with a valid text reference,
    When the command is parsed,
    Then the parser should correctly parse the command and parameters.

    Test cases include:
    - Text reference within the global text range.
    - Text reference within the loaded text range.
    - Text reference at the lower bound of the loaded text range.
    """
    script = f"""
        VC_EMPTY
        VC_I 7
        VC_IB 2 3
        VC_NT 10 {text_num}
    """
    text_range = range(range_min, range_max)
    expected_output = [
        Command(0x00, 'VC_EMPTY', ()),
        Command(0x01, 'VC_I', (Param('I', '7'),)),
        Command(0x02, 'VC_IB', (Param('I', '2'), Param('B', 3))),
        Command(0x03, 'VC_NT', (Param('N', 10), Param('T', text_num))),
    ]
    assert list(parse_cmds(script.split(), parser, text_range)) == expected_output
