from collections.abc import Mapping, Sequence

from hypothesis import given
from hypothesis import strategies as st

from magos.agos_opcode import (
    feeble_ops,
    simon2_ops,
    simon2_ops_talkie,
    simon_ops,
    simon_ops_talkie,
    waxworks_ops,
)
from magos.parser.params import (
    BASE_MIN,
    Param,
)
from magos.parser.script import (
    Command,
    Parser,
    parse_cmds,
)

# Strategies for generating command parameters
param_strategies = {
    'T': st.one_of(
        st.sampled_from([-1, -3]),
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

example_ops = {
    0x00: ('VC_EMPTY', ' '),
    0x01: ('VC_I', 'I '),
    0x02: ('VC_IB', 'IB '),
    0x03: ('VC_NT', 'NT '),
}

# Strategy for selecting an optable
optables = st.sampled_from(
    [
        example_ops,
        feeble_ops,
        simon2_ops,
        simon2_ops_talkie,
        simon_ops,
        simon_ops_talkie,
        waxworks_ops,
    ]
)


def create_command_strategy(
    item: tuple[int, tuple[str | None, str]],
    loaded_texts: tuple[int, int],
) -> st.SearchStrategy[tuple[int, str, Sequence[tuple[str, str]]]]:
    """
    Create a strategy for a single command based on the opcode table entry.
    """
    opcode, (command, params) = item
    min_loaded_text, max_loaded_text = loaded_texts

    return st.tuples(
        st.just(opcode),
        st.just(command),
        st.tuples(
            *[
                st.tuples(
                    st.just(param),
                    st.one_of(
                        param_strategies[param],
                        (
                            st.integers(
                                min_value=min_loaded_text,
                                max_value=max_loaded_text,
                            )
                            if param == 'T'
                            else param_strategies[param]
                        ),
                    ),
                )
                for param in params.rstrip()
            ]
        ),
    )


def generate_command_strategy(
    optable: Mapping[int, tuple[str | None, str]],
    loaded_texts: tuple[int, int],
) -> st.SearchStrategy[tuple[int, str, Sequence[tuple[str, str]]]]:
    """
    Generate a strategy for creating commands based on the opcode table.
    """
    valid_commands = [(key, val) for key, val in optable.items() if val[0] is not None]
    return st.sampled_from(valid_commands).flatmap(
        lambda item: create_command_strategy(item, loaded_texts)
    )


@st.composite
def generate_loaded_text_range(
    draw: 'st.DrawFn',
) -> tuple[int, int]:
    """
    Generate a random range of BASE_MIN..2**16 as a tuple (min, max).
    """
    start = draw(st.integers(min_value=BASE_MIN, max_value=2**16 - 2))
    end = draw(st.integers(min_value=start + 1, max_value=2**16 - 1))
    return start, end


whitespace = st.text(alphabet=' \t\n\v\f\r', min_size=1)


@st.composite
def valid_scripts(
    draw: 'st.DrawFn',
    optables: 'st.SearchStrategy[Mapping[int, tuple[str | None, str]]]' = optables,
) -> tuple[str, list[Command], Mapping[int, tuple[str | None, str]], tuple[int, int]]:
    """
    Generate a valid script composed of multiple commands in various formats.
    """
    optable = draw(optables)
    loaded_texts = draw(generate_loaded_text_range())

    commands = draw(
        st.lists(
            generate_command_strategy(optable, loaded_texts),
            min_size=1,
            max_size=10,
        )
    )

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
    return (
        text,
        [
            Command(
                opcode, command, tuple(Param(ptype, value) for ptype, value in params)
            )
            for opcode, command, params in commands
        ],
        optable,
        loaded_texts,
    )


@given(expected=valid_scripts())
def test_valid_script(
    expected: tuple[
        str,
        list[Command],
        Mapping[int, tuple[str | None, str]],
        tuple[int, int],
    ],
) -> None:
    """
    Test that the parser correctly identifies and parses the command
    in a valid script composed of multiple commands in any supported format.
    """
    script, parsed, optable, loaded_texts = expected
    min_loaded_text, max_loaded_text = loaded_texts
    assert (
        list(
            parse_cmds(
                script.split(),
                Parser(optable),
                range(min_loaded_text, max_loaded_text + 1),
            ),
        )
        == parsed
    )
