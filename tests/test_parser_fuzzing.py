from collections.abc import Callable, Mapping, Sequence
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from magos.agos_opcode import simon_ops
from magos.gamepc_script import BASE_MIN, Command, Param, Parser, parse_cmds

# Opcode table for command parsing
opcode_table = {
    0x00: ('VC_EMPTY', ' '),
    0x01: ('VC_I', 'I '),
    0x02: ('VC_IB', 'IB '),
    0x03: ('VC_NT', 'NT '),
}

# Strategies for generating command parameters
param_strategies = {
    'T': st.one_of(
        st.sampled_from([-1, -3]),
        # TODO: Add loaded text references to test
        # st.integers(min_value=BASE_MIN, max_value=2**16 - 1),
        st.integers(min_value=0, max_value=BASE_MIN - 1),
    ),
    'B': st.one_of(
        st.integers(min_value=0, max_value=254),
        st.integers(min_value=0, max_value=255).map(lambda x: [x]),
    ),
    'I': st.one_of(
        st.sampled_from(['$1', '$2', '$ME', '$AC', '$RM']),
        st.integers(min_value=2, max_value=2**16 - 1).map(lambda x: f'<{x}>'),
    ),
    'v': st.integers(min_value=0, max_value=2**16 - 1),
    'p': st.integers(min_value=0, max_value=2**16 - 1),
    'n': st.integers(min_value=0, max_value=2**16 - 1),
    'a': st.integers(min_value=0, max_value=2**16 - 1),
    'S': st.integers(min_value=0, max_value=2**16 - 1),
    'N': st.integers(min_value=0, max_value=2**16 - 1),
}


def generate_command_strategy(
    optable: Mapping[int, tuple[str, str]],
) -> st.SearchStrategy[tuple[int, str, Sequence[tuple[str, str]]]]:
    """
    Generate a strategy for creating commands based on the opcode table.
    """
    return st.one_of(
        [
            st.tuples(
                st.just(opcode),
                st.just(command),
                st.tuples(
                    *(
                        st.tuples(st.just(param), param_strategies[param])
                        for param in params.rstrip()
                    ),
                ),
            )
            for opcode, (command, params) in optable.items()
            if command is not None
        ],
    )

# Strategy for generating lists of commands
commands = st.lists(generate_command_strategy(simon_ops))
# Strategy for generating whitespace characters
whitespace = st.text(alphabet=' \t\n\v\f\r', min_size=1)

@st.composite
def valid_scripts(
    draw: Callable[[st.SearchStrategy], Any],
    elements: st.SearchStrategy = commands,
) -> tuple[str, list[tuple[int, str, Sequence[tuple[str, str]]]]]:
    """
    Generate a valid script composed of multiple commands in various formats.
    including newline-separated, space-separated, mixed whitespace
    and optional opcode prefixes.
    """
    commands = draw(elements)
    script = [
        ' '.join(
            [
                *((f'({hex(opcode)})',) if draw(st.booleans()) else ()),
                command,
                *(str(x) for _, x in params),
            ],
        )
        for opcode, command, params in commands
    ]

    text = ''.join(draw(whitespace) + line + draw(whitespace) for line in script)
    return text, [
        Command(opcode, command, tuple(Param(ptype, value) for ptype, value in params))
        for opcode, command, params in commands
    ]


@given(expected=valid_scripts())
def test_valid_script(
    expected: tuple[str, list[tuple[int, str, Sequence[tuple[str, str]]]]],
) -> None:
    """
    Test that the parser correctly identifies and parses the command
    in a valid script composed of multiple commands in any supported format.
    """
    script, parsed = expected
    assert (
        list(
            parse_cmds(
                script.split(),
                Parser(simon_ops),
                range(BASE_MIN, BASE_MIN + 1),
            ),
        )
        == parsed
    )
