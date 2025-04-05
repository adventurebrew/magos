import argparse
import io
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import tomli
import tomli_w
import urwid  # type: ignore[import-untyped]

from magos.chiper import RAW_BYTE_ENCODING, EncodeSettings, decrypts
from magos.detection import (
    DetectionEntry,
    GameNotDetectedError,
    auto_detect_game_from_filenames,
    known_variants,
)
from magos.interactive.directory import DirectorySelector
from magos.interactive.widgets import (
    FeaturesWidget,
    GameSelectionWidget,
    LanguageWidget,
    TextOutputWidget,
)
from magos.magos import CLIParams, OptionalFileAction
from magos.magos import main as magos_main

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence


@dataclass
class InteractiveCLIParams(CLIParams):
    non_interactive: bool = False


@contextmanager
def redirect_stdout_stderr(file: 'IO[str]') -> 'Iterator[None]':
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = file
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


def validate_config(config: 'dict[str, Any]') -> None:
    config['selected_game'] = known_variants[config['selected_game']].name


def load_directory_config(directory: Path) -> 'dict[str, Any]':
    """Load the state from a configuration file in the directory."""
    config_path = directory / 'magos.toml'
    error_stream = sys.stderr
    if not config_path.exists():
        return {}
    try:
        with config_path.open('rb') as config_file:
            config_data = tomli.load(config_file)
        validate_config(config_data)
    except Exception as e:  # noqa: BLE001
        print(
            'WARNING: Could not load configuration file:',
            e,
            file=error_stream,
        )
        return {}
    return config_data


def run_magos(
    directory: Path,
    game: str | None,
    state: 'dict[str, Any]',
    *,
    rebuild: bool,
) -> bool:
    encoding = state['encoding']
    convert_utf8 = state['convert_utf8']
    text_output = state['text_output']

    extract_directory = None
    if state.get('archive', {}).get('selected'):
        cont = state['archive']['content']
        extract_directory = cont['extract_directory']

    scripts = None
    objects = Path('objects.txt')
    if state.get('scripts', {}).get('selected'):
        cont = state['scripts']['content']
        assert cont
        scripts = Path(cont['scripts_output'])
        objects = Path(cont['objects_output'])

    voices = []
    if state.get('voices', {}).get('selected'):
        cont = state['voices']['content']
        voices = [str(x) for x in cont['files']]

    return magos_main(
        CLIParams(
            path=directory,
            crypt=encoding if encoding != 'en' else None,
            output=Path(text_output),
            extract=extract_directory,
            game=game,
            script=scripts,
            items=objects,
            voice=voices,
            rebuild=rebuild,
            unicode=convert_utf8,
        )
    )


class InteractiveMagos:
    def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
        self.state_tracker: dict[str, Any] = {
            'encoding': 'en',
            'convert_utf8': True,
            'text_output': 'strings.txt',
            'selected_directory': Path.cwd(),
        }
        if initial_state:
            self.configure_directory(initial_state['selected_directory'])
            self.state_tracker.update(initial_state)

        self.output_content = None
        self.output_content_box = None
        self.program_output = ''
        self.output_type_list = None
        self.output_frame = None

        self.palette = [
            ('reversed', 'standout', ''),
            ('bold', 'default,bold', ''),
        ]

    def run(self) -> None:
        self.loop = urwid.MainLoop(
            None,
            palette=self.palette,
            unhandled_input=self.unhandled_input,
        )
        if self.state_tracker['selected_game'] is None:
            self.show_game_selection_screen()
        else:
            self.show_main_screen()
        self.loop.run()

    def save_directory_config(self, directory: Path) -> None:
        """Save relevant state to a configuration file in the directory."""
        config_path = directory / 'magos.toml'
        config_data = {
            key: self.state_tracker[key]
            for key in [
                'selected_game',
                'encoding',
                'convert_utf8',
                'text_output',
                'scripts',
                'archive',
                'voices',
            ]
            if key in self.state_tracker
        }
        with config_path.open('wb') as config_file:
            tomli_w.dump(config_data, config_file)

            self.state_tracker.update(config_data)

    def configure_directory(self, path: str | Path) -> None:
        """Configure the selected directory and load its configuration."""
        self.state_tracker['selected_directory'] = Path(path)
        self.state_tracker.update(
            load_directory_config(self.state_tracker['selected_directory']),
        )
        try:
            self.state_tracker['detected_game'] = auto_detect_game_from_filenames(
                self.state_tracker['selected_directory']
            )
        except GameNotDetectedError:
            self.state_tracker['detected_game'] = None

        # Prefer `selected_game` from the configuration if available
        detected = self.state_tracker['detected_game']
        game_key = detected and detected.name
        self.state_tracker['selected_game'] = (
            self.state_tracker.get('selected_game') or game_key
        )

    def on_exit(self, button: urwid.Button) -> None:
        raise urwid.ExitMainLoop

    def update_output_content(self, text: str) -> None:
        lines = text.splitlines()
        assert self.output_content is not None
        self.output_content.body = urwid.SimpleFocusListWalker(
            [urwid.Text(line) for line in lines]
        )

    def get_file_encoding(self) -> EncodeSettings:
        if self.state_tracker['convert_utf8']:
            return EncodeSettings(encoding='utf-8', errors='strict')
        if self.state_tracker['encoding'] == 'en':
            return RAW_BYTE_ENCODING
        return decrypts[self.state_tracker['encoding']][1]

    def on_set_output_type(self, button: urwid.Button) -> None:
        output_type = button.label
        assert self.output_content is not None
        assert self.output_content_box is not None
        source = self.program_output
        encoding = self.get_file_encoding()
        final_path = None
        if output_type == 'Text Output':
            text_path = Path(self.state_tracker['text_output'])
            final_path = text_path
        script_path = None
        objects_path = None
        if self.state_tracker.get('scripts', {}).get('selected'):
            script_path = Path(
                self.state_tracker['scripts']['content']['scripts_output']
            )
            objects_path = Path(
                self.state_tracker['scripts']['content']['objects_output']
            )
        if output_type == 'Scripts Output':
            if not script_path:
                source = 'ERROR: Script output path is not configured.'
            else:
                final_path = script_path
        if output_type == 'Objects Output':
            if not objects_path:
                source = 'ERROR: Objects output path is not configured.'
            else:
                final_path = objects_path
        if final_path:
            try:
                source = final_path.read_text(**encoding)
            except FileNotFoundError:
                source = f'ERROR: Could not find {final_path}.'
            except UnicodeDecodeError:
                source = (
                    f'ERROR: Could not read from {final_path} with configured encoding.'
                )
        self.update_output_content(
            source.expandtabs(
                tabsize=4 if output_type in {'Scripts Output', 'Objects Output'} else 8
            )
        )
        self.output_content_box.set_title(f' {output_type} ')

    def show_main_screen(self) -> None:
        selected_game = self.state_tracker['selected_game']
        assert selected_game is not None
        assert isinstance(selected_game, str)
        assert selected_game in known_variants

        features_widget = FeaturesWidget(self.state_tracker)

        output_types = [
            'Program Output',
            'Text Output',
            'Scripts Output',
            'Objects Output',
        ]

        self.output_type_list = urwid.ListBox(
            urwid.SimpleFocusListWalker(
                [
                    urwid.AttrMap(
                        urwid.Button(output_type, self.on_set_output_type),
                        None,
                        focus_map='reversed',
                    )
                    for output_type in output_types
                ]
            )
        )

        self.output_content = urwid.ListBox(
            urwid.SimpleFocusListWalker([urwid.Text(self.program_output)])
        )

        def on_print(button: urwid.Button, button_label: str) -> None:
            assert self.output_content is not None
            features_widget.update_inner_state()
            selected_directory = self.state_tracker['selected_directory']

            self.update_output_content('...Running...')
            self.output_type_list.set_focus(0)
            assert self.output_content_box is not None
            self.output_content_box.set_title(' Program Output ')
            self.loop.draw_screen()

            try:
                with io.StringIO() as file, redirect_stdout_stderr(file):
                    exit_with_error = run_magos(
                        selected_directory,
                        selected_game,
                        self.state_tracker,
                        rebuild=button_label == 'Rebuild',
                    )
                    self.program_output = file.getvalue().expandtabs()
                    self.update_output_content(self.program_output)
                    self.output_type_list.set_focus(0)
                    self.output_content_box.set_title(' Program Output ')

            except Exception as e:  # noqa: BLE001
                self.update_output_content(f'ERROR: {e!r}')
            else:
                # Save configuration only after successful action
                if not exit_with_error:
                    self.save_directory_config(selected_directory)

        exit_button = urwid.Button('Exit', on_press=self.on_exit)
        print_button1 = urwid.Button(
            'Extract', on_press=lambda button: on_print(button, 'Extract')
        )
        print_button2 = urwid.Button(
            'Rebuild', on_press=lambda button: on_print(button, 'Rebuild')
        )

        buttons = urwid.Columns(
            [
                urwid.Columns([('fixed', 20, exit_button), urwid.Text('')]),
                urwid.Columns([print_button1, print_button2], dividechars=5),
            ],
            dividechars=1,
        )

        change_directory_button = urwid.Button(
            'Change',
            on_press=self.show_directory_selection_screen,
        )
        directory_display = urwid.Text(str(self.state_tracker['selected_directory']))
        directory_section = urwid.LineBox(
            urwid.Columns(
                [('fixed', 20, change_directory_button), directory_display],
                dividechars=5,
            ),
            ' Game Directory ',
            'left',
        )

        change_game_button = urwid.Button(
            'Change',
            on_press=self.show_game_selection_screen,
        )
        game_display = urwid.Text(
            str(known_variants[self.state_tracker['selected_game']]),
        )
        game_section = urwid.LineBox(
            urwid.Columns(
                [('fixed', 20, change_game_button), game_display], dividechars=5
            ),
            ' Detected Game ',
            'left',
        )

        encoding_section = urwid.LineBox(
            LanguageWidget(['en', *decrypts], self.state_tracker),
            ' Language ',
            'left',
        )
        text_output_edit_box = urwid.LineBox(
            TextOutputWidget(self.state_tracker), ' Texts ', 'left'
        )

        top_widgets = urwid.LineBox(
            urwid.Pile(
                [
                    directory_section,
                    game_section,
                    urwid.Columns(
                        [
                            urwid.Pile(
                                [
                                    text_output_edit_box,
                                    features_widget,
                                ],
                                focus_item=1,
                            ),
                            encoding_section,
                        ]
                    ),
                ],
                focus_item=2,
            )
        )

        self.output_content_box = urwid.LineBox(
            urwid.BoxAdapter(urwid.ScrollBar(self.output_content), height=9),
            ' Program Output ',
            'left',
        )
        self.output_frame = urwid.LineBox(
            urwid.Columns(
                [
                    (
                        'fixed',
                        20,
                        urwid.LineBox(
                            urwid.BoxAdapter(
                                self.output_type_list,
                                height=len(output_types),
                            ),
                        ),
                    ),
                    self.output_content_box,
                ],
            ),
            'Output ',
            'left',
        )

        main_layout = urwid.Pile(
            [
                top_widgets,
                urwid.LineBox(buttons, ' Actions ', 'left'),
                self.output_frame,
            ]
        )

        filler = urwid.Filler(main_layout, valign='top')
        self.loop.widget = filler

    def on_game_selected(self, game: DetectionEntry) -> None:
        if self.state_tracker['selected_game'] != game.name:
            self.state_tracker['selected_game'] = game.name
            # Reset features if the game changes
            self.state_tracker.pop('scripts', None)
            self.state_tracker.pop('archive', None)
            self.state_tracker.pop('voices', None)
        self.show_main_screen()

    def show_game_selection_screen(self, button: urwid.Button = None) -> None:
        game_selection_widget = urwid.LineBox(
            GameSelectionWidget(
                self.state_tracker,
                list(known_variants.values()),
                self.on_game_selected,
            ),
            ' Detected Game ',
            'left',
        )

        change_directory_button = urwid.Button(
            'Change',
            on_press=self.show_directory_selection_screen,
        )
        directory_display = urwid.Text(str(self.state_tracker['selected_directory']))
        directory_section = urwid.LineBox(
            urwid.Columns(
                [('fixed', 20, change_directory_button), directory_display],
                dividechars=5,
            ),
            ' Game Directory ',
            'left',
        )

        exit_button = urwid.Button('Exit', on_press=self.on_exit)

        exit_button_box = urwid.LineBox(
            urwid.Columns(
                [
                    urwid.Columns([('fixed', 20, exit_button), urwid.Text('')]),
                    urwid.Text(''),
                ],
                dividechars=1,
            ),
            ' Actions ',
            'left',
        )

        layout = urwid.LineBox(
            urwid.Pile(
                [directory_section, game_selection_widget, exit_button_box],
                focus_item=1,
            )
        )
        self.loop.widget = urwid.Filler(layout, valign='top')

    def on_directory_selected(self, path: str | Path) -> None:
        self.configure_directory(path)
        if self.state_tracker['selected_game'] is None:
            self.show_game_selection_screen()
        else:
            self.show_main_screen()

    def show_directory_selection_screen(self, button: urwid.Button = None) -> None:
        directory_selection_widget = DirectorySelector(
            self.state_tracker['selected_directory']
        )

        urwid.connect_signal(
            directory_selection_widget, 'selected', self.on_directory_selected
        )
        self.loop.widget = urwid.LineBox(directory_selection_widget)

    def unhandled_input(self, key: str) -> None:
        if key == 'ctrl d':
            raise urwid.ExitMainLoop


def menu(args: 'Sequence[str] | None' = None) -> InteractiveCLIParams:
    parser = argparse.ArgumentParser(description='MAGOS')
    parser.add_argument(
        'path',
        nargs='?',
        default=Path.cwd(),
        type=Path,
    )
    parser.add_argument(
        '--non-interactive',
        '-n',
        action='store_true',
        help='Run in non-interactive mode',
    )
    parser.add_argument(
        '--crypt',
        '-c',
        choices=decrypts.keys(),
        default=None,
        help='Optional text decryption method',
    )
    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        default=None,
        help='File to output game strings to (default: strings.txt)',
    )
    parser.add_argument(
        '--extract',
        '-e',
        type=Path,
        default=None,
        help='Optionally specify directory to extract file from .GME',
    )
    parser.add_argument(
        '--game',
        '-g',
        choices=known_variants.keys(),
        default=None,
        required=False,
        help=(
            'Specific game to extract '
            '(will attempt to infer from file name if not provided)'
        ),
    )
    parser.add_argument(
        '--script',
        '-s',
        nargs='?',
        type=Path,
        action=OptionalFileAction,
        default=None,
        default_path=Path('scripts.txt'),
        help='File to output game scripts to (default: scripts.txt)',
    )
    parser.add_argument(
        '--items',
        '-i',
        type=Path,
        default=None,
        help='File to output game items to (default: objects.txt)',
    )
    parser.add_argument(
        '--voice',
        '-t',
        nargs='+',
        type=str,
        default=(),
        help='Sound file(s) with voices to extract',
    )
    parser.add_argument(
        '--rebuild',
        '-r',
        action='store_true',
        help='Rebuild modified game resources',
    )
    parser.add_argument(
        '--unicode',
        '-u',
        action='store_true',
        help='Convert output to unicode',
    )

    pargs = parser.parse_args(args)
    default_values = {
        'items': Path('objects.txt'),
        'output': Path('strings.txt'),
    }
    for key in default_values:
        if getattr(pargs, key) is None:
            setattr(pargs, key, default_values[key])
        else:
            pargs.non_interactive = True

    return InteractiveCLIParams(**vars(pargs))


def main() -> None:
    args = menu()

    initial_state: dict[str, Any] = {
        'selected_directory': args.path,
    }
    if args.crypt:
        initial_state['encoding'] = args.crypt
    if args.output is not None:
        initial_state['text_output'] = str(args.output)
    if args.game:
        initial_state['selected_game'] = args.game
    if args.script:
        initial_state['scripts'] = {
            'selected': True,
            'content': {
                'scripts_output': str(args.script),
                'objects_output': str(args.items),
            },
        }

    # Determine mode based on parsed arguments
    non_interactive_mode = (
        args.non_interactive
        or args.script
        or args.voice
        or args.crypt
        or args.extract
        or args.rebuild
    )

    if non_interactive_mode:
        # Non-interactive mode
        state = load_directory_config(args.path)
        state['encoding'] = state.get('encoding', args.crypt)
        state['convert_utf8'] = state.get('convert_utf8', args.unicode)
        if args.voice:
            state['voices'] = {
                'selected': True,
                'content': {
                    'files': args.voice,
                },
            }
        if args.extract:
            state['archive'] = {
                'selected': True,
                'content': {
                    'extract_directory': args.extract,
                },
            }
        state.update(initial_state)
        sys.exit(
            run_magos(
                args.path,
                state.get('selected_game'),
                state,
                rebuild=args.rebuild,
            )
        )
    else:
        # Interactive mode
        InteractiveMagos(initial_state).run()


if __name__ == '__main__':
    main()
