import itertools
from collections.abc import Callable, Iterator, Sequence
from typing import Any, ClassVar

import urwid  # type: ignore[import-untyped]


class CheckboxWithContent(urwid.WidgetWrap):  # type: ignore[misc]
    signals: ClassVar[list[str]] = ['change']

    def __init__(
        self,
        label: str,
        content: urwid.Widget,
    ) -> None:
        self.checkbox = urwid.CheckBox(
            label, state=False, on_state_change=self.on_checkbox_change
        )
        self.content = content
        self.content_widget = urwid.Columns(
            [('fixed', 20, self.checkbox)], dividechars=5
        )
        super().__init__(self.content_widget)

    def on_checkbox_change(self, checkbox: urwid.CheckBox, state: bool) -> None:  # noqa: FBT001
        if state:
            self.content_widget.contents.append(
                (self.content, self.content_widget.options())
            )
        else:
            self.content_widget.contents = [
                (self.checkbox, self.content_widget.options('given', 20))
            ]
        self._emit('change', state)


language_pretty_names = {
    'en': 'English',
    'he': 'Hebrew',
    'de': 'German',
    'es': 'Spanish',
    'fr': 'French',
    'it': 'Italian',
    'pl': 'Polish',
    'ru': 'Russian',
}
inverse_lang_lookup = {value: key for key, value in language_pretty_names.items()}


class LanguageWidget(urwid.WidgetWrap):  # type: ignore[misc]
    def __init__(
        self, options: Sequence[str] | dict[str, Any], state_tracker: dict[str, Any]
    ) -> None:
        self.state_tracker = state_tracker
        self.options = (
            {key: None for key in options} if not isinstance(options, dict) else options
        )
        self.widget = self.create_widget()
        super().__init__(self.widget)

    def create_widget(self) -> urwid.Widget:
        radio_button_group: list[urwid.RadioButton] = []
        radio_buttons = [
            urwid.RadioButton(
                radio_button_group,
                language_pretty_names[key],
                state=(key == self.state_tracker['encoding']),
                on_state_change=self.on_radio_change,
                user_data=value,
            )
            for key, value in self.options.items()
        ]

        # Create the layout with Columns and Pile
        radio_buttons_list = urwid.BoxAdapter(
            urwid.ListBox(urwid.SimpleFocusListWalker(radio_buttons)),
            height=len(radio_buttons),
        )

        return urwid.Pile(
            [
                radio_buttons_list,
            ]
        )

    def on_radio_change(self, radio_button: urwid.RadioButton, state: bool) -> None:  # noqa: FBT001
        if state:
            label = radio_button.get_label()
            self.state_tracker['encoding'] = inverse_lang_lookup[label]


class TextOutputWidget(urwid.WidgetWrap):  # type: ignore[misc]
    def __init__(self, state_tracker: dict[str, Any]) -> None:
        self.state_tracker = state_tracker
        self.checkbox = urwid.CheckBox(
            'Convert UTF-8',
            state=self.state_tracker['convert_utf8'],
            on_state_change=self.on_checkbox_change,
        )
        self.edit = urwid.Edit(edit_text=state_tracker['text_output'])
        urwid.connect_signal(self.edit, 'change', self.on_text_change)
        self.widget = urwid.Columns(
            [
                ('fixed', 20, self.checkbox),
                urwid.Columns(
                    [
                        ('fixed', 15, urwid.Text('Strings Output:')),
                        self.edit,
                    ],
                    dividechars=2,
                ),
            ],
            dividechars=5,
        )
        super().__init__(self.widget)

    def on_text_change(self, edit: urwid.Edit, new_text: str) -> None:
        self.state_tracker['text_output'] = new_text

    def on_checkbox_change(self, checkbox: urwid.CheckBox, state: bool) -> None:  # noqa: FBT001
        self.state_tracker['convert_utf8'] = state


class FeaturesWidget(urwid.WidgetWrap):  # type: ignore[misc]
    def __init__(self, state_tracker: dict[str, Any]) -> None:
        self.state_tracker = state_tracker
        self.widgets = dict(self.create_widgets())
        pile = urwid.Pile(self.widgets.values())
        super().__init__(pile)

    def create_widgets(self) -> Iterator[tuple[str, urwid.Widget]]:
        features = ['scripts']

        selected_game = self.state_tracker['selected_game']
        if selected_game.archive is not None:
            features.append('archive')
        else:
            self.state_tracker.pop('archive', None)

        voice_patterns = ['*.VOC', '*.WAV', '*.MP3', '*.OGG', '*.FLA']
        voice_files = sorted(
            set(
                itertools.chain.from_iterable(
                    self.state_tracker['selected_directory'].glob(pattern)
                    for pattern in voice_patterns
                )
            ),
        )
        if voice_files:
            features.append('voices')
        else:
            self.state_tracker.pop('voices', None)

        for feature in features:
            if feature == 'scripts':
                self.state_tracker['scripts'] = {'selected': False, 'content': {}}
                self.scripts_output_field = urwid.Edit(
                    edit_text=self.state_tracker['scripts']['content'].get(
                        'scripts_output', 'scripts.txt'
                    ),
                )
                self.objects_output_field = urwid.Edit(
                    edit_text=self.state_tracker['scripts']['content'].get(
                        'objects_output', 'objects.txt'
                    ),
                )
                content1 = urwid.Pile(
                    [
                        urwid.Columns(
                            [
                                ('fixed', 15, urwid.Text('Scripts Output:')),
                                self.scripts_output_field,
                            ],
                            dividechars=2,
                        ),
                        urwid.Columns(
                            [
                                ('fixed', 15, urwid.Text('Objects Output:')),
                                self.objects_output_field,
                            ],
                            dividechars=2,
                        ),
                    ]
                )
                checkbox1 = CheckboxWithContent(
                    'Scripts',
                    content1,
                )
                urwid.connect_signal(checkbox1, 'change', self.on_opt1_change)
                yield 'scripts', urwid.LineBox(checkbox1)
            elif feature == 'archive':
                self.state_tracker['archive'] = {'selected': False, 'content': {}}
                self.extract_dir_field = urwid.Edit(
                    edit_text=self.state_tracker['archive']['content'].get(
                        'extract_directory', 'ext'
                    )
                )
                content2 = urwid.Columns(
                    [
                        ('fixed', 15, urwid.Text('Extracted Path:')),
                        self.extract_dir_field,
                    ],
                    dividechars=2,
                )
                checkbox2 = CheckboxWithContent(
                    'Packed Archive',
                    content2,
                )
                urwid.connect_signal(checkbox2, 'change', self.on_opt2_change)
                yield 'archive', urwid.LineBox(checkbox2)
            elif feature == 'voices':
                self.state_tracker['voices'] = {'selected': False, 'content': {}}
                self.voices = urwid.Pile(
                    [urwid.CheckBox(voicefile.name) for voicefile in voice_files]
                )
                checkbox3 = CheckboxWithContent(
                    'Voices',
                    self.voices,
                )
                urwid.connect_signal(checkbox3, 'change', self.on_opt3_change)
                yield 'voices', urwid.LineBox(checkbox3)

    def on_opt1_change(self, checkbox: CheckboxWithContent, state: bool) -> None:  # noqa: FBT001
        self.state_tracker['scripts']['selected'] = state
        self.state_tracker['scripts']['content']['scripts_output'] = (
            self.scripts_output_field.edit_text
        )
        self.state_tracker['scripts']['content']['objects_output'] = (
            self.objects_output_field.edit_text
        )

    def on_opt2_change(self, checkbox: CheckboxWithContent, state: bool) -> None:  # noqa: FBT001
        self.state_tracker['archive']['selected'] = state
        self.state_tracker['archive']['content']['extract_directory'] = (
            self.extract_dir_field.edit_text
        )

    def on_opt3_change(self, checkbox: CheckboxWithContent, state: bool) -> None:  # noqa: FBT001
        self.state_tracker['voices']['selected'] = state
        self.state_tracker['voices']['content']['files'] = [
            check.get_label() for check, _ in self.voices.contents if check.state
        ]

    def update_inner_state(self) -> None:
        for key in self.widgets:
            if key == 'scripts':
                self.state_tracker[key]['content']['scripts_output'] = (
                    self.scripts_output_field.edit_text
                )
                self.state_tracker[key]['content']['objects_output'] = (
                    self.objects_output_field.edit_text
                )
            if key == 'archive':
                self.state_tracker[key]['content']['extract_directory'] = (
                    self.extract_dir_field.edit_text
                )
            if key == 'voices':
                self.state_tracker['voices']['content']['files'] = [
                    check.get_label()
                    for check, _ in self.voices.contents
                    if check.state
                ]


class GameSelectionWidget(urwid.WidgetWrap):  # type: ignore[misc]
    def __init__(
        self,
        state_tracker: dict[str, Any],
        options: Sequence[Any],
        on_game_detected: Callable[[], None],
    ) -> None:
        self.state_tracker = state_tracker
        self.on_game_detected = on_game_detected
        self.options = options
        self.widget = self.create_widget()
        super().__init__(self.widget)

    def create_widget(self) -> urwid.Widget:
        radio_button_group: list[urwid.RadioButton] = []
        radio_buttons = [
            *(
                [
                    urwid.RadioButton(
                        radio_button_group,
                        str(self.state_tracker['detected_game']),
                        state=False,
                        on_state_change=self.on_radio_change,
                        user_data=self.state_tracker['detected_game'],
                    )
                ]
                if self.state_tracker['detected_game'] is not None
                else []
            ),
            *[
                urwid.RadioButton(
                    radio_button_group,
                    str(key),
                    state=False,
                    on_state_change=self.on_radio_change,
                    user_data=key,
                )
                for key in self.options
                if key != self.state_tracker['detected_game']
            ],
        ]
        helper = (
            urwid.Text('  Suggestion:')
            if self.state_tracker['detected_game']
            else urwid.Text('  Manual Selection:')
        )
        if self.state_tracker['detected_game']:
            radio_buttons[0] = urwid.AttrMap(radio_buttons[0], 'bold')
        list_walker = urwid.SimpleFocusListWalker(radio_buttons)
        list_box = urwid.ListBox(list_walker)
        list_box_adapter = urwid.BoxAdapter(
            list_box, height=len(radio_buttons) + 2
        )  # Adjust height as needed
        return urwid.Columns([('fixed', 20, helper), list_box_adapter], dividechars=5)

    def on_radio_change(
        self,
        radio_button: urwid.RadioButton,
        state: bool,  # noqa: FBT001
        user_data: Any,  # noqa: ANN401
    ) -> None:
        if state:
            self.state_tracker['selected_game'] = user_data
            self.on_game_detected()
