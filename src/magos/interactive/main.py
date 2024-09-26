import io
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

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
from magos.magos import CLIParams
from magos.magos import main as magos_main


@contextmanager
def redirect_stdout_stderr(file: IO[str]) -> Iterator[None]:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = file
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


class InteractiveMagos:
    def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
        self.state_tracker: dict[str, Any] = {
            'encoding': 'en',
            'convert_utf8': True,
            'text_output': 'strings.txt',
            'selected_directory': Path.cwd(),
        }
        if initial_state:
            self.state_tracker.update(initial_state)
            self.configure_directory(self.state_tracker['selected_directory'])

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
        if self.state_tracker['detected_game'] is None:
            self.show_game_selection_screen()
        else:
            self.show_main_screen()
        self.loop.run()

    def configure_directory(self, path: str | Path) -> None:
        self.state_tracker['selected_directory'] = Path(path)
        try:
            self.state_tracker['detected_game'] = auto_detect_game_from_filenames(
                self.state_tracker['selected_directory']
            )
        except GameNotDetectedError:
            self.state_tracker['detected_game'] = None
        self.state_tracker['selected_game'] = self.state_tracker['detected_game']

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

    def show_main_screen(self) -> None:  # noqa: PLR0915
        selected_game = self.state_tracker['selected_game']
        assert selected_game is not None
        assert isinstance(selected_game, DetectionEntry)

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
            encoding = self.state_tracker['encoding']
            convert_utf8 = self.state_tracker['convert_utf8']
            text_output = self.state_tracker['text_output']
            selected_directory = self.state_tracker['selected_directory']

            extract_directory = None
            if self.state_tracker.get('archive', {}).get('selected'):
                cont = self.state_tracker['archive']['content']
                extract_directory = cont['extract_directory']

            scripts = None
            objects = Path('objects.txt')
            if self.state_tracker.get('scripts', {}).get('selected'):
                cont = self.state_tracker['scripts']['content']
                assert cont
                scripts = Path(cont['scripts_output'])
                objects = Path(cont['objects_output'])

            voices = []
            if self.state_tracker.get('voices', {}).get('selected'):
                cont = self.state_tracker['voices']['content']
                voices = [str(x) for x in cont['files']]

            self.update_output_content('...Running...')
            self.output_type_list.set_focus(0)
            assert self.output_content_box is not None
            self.output_content_box.set_title(' Program Output ')
            self.loop.draw_screen()
            with io.StringIO() as file, redirect_stdout_stderr(file):
                magos_main(
                    CLIParams(
                        path=selected_directory,
                        crypt=encoding if encoding != 'en' else None,
                        output=Path(text_output),
                        extract=extract_directory,
                        game=selected_game.name,
                        script=scripts,
                        items=objects,
                        voice=voices,
                        rebuild=button_label == 'Rebuild',
                        unicode=convert_utf8,
                    )
                )
                self.program_output = file.getvalue().expandtabs()
                self.update_output_content(self.program_output)
                self.output_type_list.set_focus(0)
                self.output_content_box.set_title(' Program Output ')

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
        game_display = urwid.Text(str(self.state_tracker['selected_game']))
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

    def show_game_selection_screen(self, button: urwid.Button = None) -> None:
        game_selection_widget = urwid.LineBox(
            GameSelectionWidget(
                self.state_tracker, list(known_variants.values()), self.show_main_screen
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


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser('Interactive Magos')
    parser.add_argument('path', nargs='?', default=Path.cwd(), type=Path)
    args = parser.parse_args()

    path = args.path
    if not path.is_dir():
        path = path.parent
        assert path.is_dir(), f'Invalid directory: {args.path}'

    initial_state = {
        'encoding': 'en',
        'convert_utf8': True,
        'text_output': 'strings.txt',
        'selected_directory': path,
    }
    InteractiveMagos(initial_state).run()
