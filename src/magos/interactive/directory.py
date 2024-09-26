import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import urwid  # type: ignore[import-untyped]

EMOJI = os.environ.get('MAGOS_EMOJI_SUPPORT')
CLOSED_DIR_ICON = '📁' if EMOJI else ''
OPEN_DIR_ICON = '📂' if EMOJI else ''
FILE_ICON = '📄' if EMOJI else ''
BLOCKED_ICON = '🚫' if EMOJI else ''


class DirectoryButton(urwid.Button):  # type: ignore[misc]
    button_left: urwid.Widget = urwid.Text('>')
    button_right: urwid.Widget = urwid.Text('')
    selected: ClassVar[urwid.Button] = None

    @classmethod
    def set_selected(cls, button: urwid.Button) -> None:
        cls.selected = button

    @classmethod
    def get_selected(cls) -> urwid.Button:
        return cls.selected

    def __init__(
        self, label: str, *args: Any, icon: str = OPEN_DIR_ICON, **kwargs: Any
    ) -> None:
        self.icon = icon
        super().__init__(f'{self.icon} {label}', *args, **kwargs)

    def get_label(self) -> str:
        label = super().get_label()
        assert isinstance(label, str)
        return label.removeprefix(f'{self.icon} ')

    def keypress(self, size: tuple[int, int], key: str) -> str:
        prev_selected = self.get_selected()
        key = super().keypress(size, key)
        self.set_selected(self)
        if key is None and prev_selected != self:
            self._emit('click')
        return key


EDIT_MODE_INSTRUCTIONS = "Type the path. Press 'Esc' to exit."
SELECTION_MODE_INSTRUCTIONS = (
    "Press 'Enter' to select, 'Backspace' to go up, 'C' to confirm, "
    "'T' to type path, 'Ctrl+D' to quit"
)
CONFIRMED_MODE_INSTRUCTIONS = (
    "Press 'R' to return to directory selection, 'Ctrl+D' to quit"
)


class DirectorySelector(urwid.WidgetWrap):  # type: ignore[misc]
    signals: ClassVar[Sequence[str]] = ['selected']

    def __init__(self, initial_dir: Path | None = None) -> None:
        self.current_dir = initial_dir or Path.cwd()
        self.selected_dir = self.current_dir
        self.typing_mode = False
        self.walker = urwid.SimpleFocusListWalker(self.get_directory_items())
        self.listbox = urwid.ScrollBar(urwid.ListBox(self.walker))
        self.file_walker = urwid.SimpleListWalker(self.get_file_items())
        self.file_listbox = urwid.ScrollBar(urwid.ListBox(self.file_walker))
        self.header = urwid.Edit(edit_text=str(self.current_dir))
        self.footer = urwid.Text(SELECTION_MODE_INSTRUCTIONS)
        self.select_button = urwid.Button('Select', self.on_confirm_button_click)

        self.view = urwid.Frame(
            urwid.AttrMap(
                urwid.Columns(
                    [
                        urwid.AttrMap(urwid.LineBox(self.listbox), 'frame'),
                        urwid.AttrMap(urwid.LineBox(self.file_listbox), 'frame'),
                    ],
                ),
                'body',
            ),
            header=urwid.LineBox(
                urwid.Columns(
                    [
                        (
                            'fixed',
                            20,
                            urwid.AttrMap(self.select_button, 'frame'),
                        ),
                        urwid.AttrMap(self.header, 'frame'),
                    ],
                    dividechars=5,
                    focus_column=1,
                ),
                ' Game Directory ',
                'left',
            ),
            footer=urwid.AttrMap(self.footer, 'footer'),
        )
        urwid.connect_signal(self.header, 'postchange', self.on_path_change)
        super().__init__(self.view)

    def on_path_change(self, _edit: urwid.Edit, new_edit_text: str) -> None:
        self.handle_path_input()

    def get_directory_items(self) -> list[urwid.AttrMap]:
        items = []
        if str(self.current_dir) != self.current_dir.root:
            item = DirectoryButton('..', self.click_directory)
            items.append(urwid.AttrMap(item, None, focus_map='reversed'))
        for entry in self.current_dir.iterdir():
            if entry.is_dir():
                if os.access(entry, os.R_OK):
                    item = DirectoryButton(
                        entry.name,
                        self.click_directory,
                        icon=CLOSED_DIR_ICON,
                    )
                    items.append(urwid.AttrMap(item, None, focus_map='reversed'))
                else:
                    item = urwid.Text(f'- {BLOCKED_ICON} {entry.name} (no access)')
                    items.append(urwid.AttrMap(item, None, focus_map='reversed'))
        return items

    def get_file_items(self) -> list[urwid.Text]:
        items = [
            urwid.Text(f'{FILE_ICON} {entry.name}')
            for entry in self.current_dir.iterdir()
            if entry.is_file()
        ]
        return items

    def click_directory(self, button: DirectoryButton) -> None:
        if button.get_selected() == button:
            self.change_directory(button)
        else:
            button.set_selected(button)
            self.exit_path_mode()

    def change_directory(self, button: urwid.Button) -> None:
        selected_dir = button.get_label()
        if selected_dir == '..':
            self.current_dir = self.current_dir.parent
        else:
            self.current_dir = self.current_dir / selected_dir
        self.header.set_edit_text(str(self.current_dir))
        self.walker[:] = self.get_directory_items()
        self.file_walker[:] = self.get_file_items()
        self.exit_path_mode()

    def on_confirm_button_click(self, button: urwid.Button) -> None:
        self.confirm_selection()

    def confirm_selection(self) -> None:
        self.selected_dir = self.current_dir
        self.header = urwid.Text(f'Current Directory: {self.selected_dir}')
        self.view.header = urwid.AttrMap(urwid.LineBox(self.header), 'frame')
        self.footer.set_text(CONFIRMED_MODE_INSTRUCTIONS)
        self.view.body = urwid.Filler(urwid.Text(str(self.selected_dir)))
        urwid.emit_signal(self, 'selected', self.selected_dir)

    def return_to_selection(self) -> None:
        self.header = urwid.Edit('Current Directory: ', edit_text=str(self.current_dir))
        urwid.connect_signal(self.header, 'postchange', self.on_path_change)
        self.view.header = urwid.AttrMap(urwid.LineBox(self.header), 'frame')
        self.footer.set_text(SELECTION_MODE_INSTRUCTIONS)
        self.view.body = urwid.Columns(
            [
                ('weight', 1, urwid.AttrMap(urwid.LineBox(self.listbox), 'frame')),
                ('weight', 1, urwid.AttrMap(urwid.LineBox(self.file_listbox), 'frame')),
            ],
        )

    def enter_path_mode(self) -> None:
        self.typing_mode = True
        self.header.set_edit_text(str(self.current_dir))
        self.header.set_edit_pos(len(self.header.get_edit_text()))
        self.footer.set_text("Type the path. Press 'Esc' to exit.")
        self.view.set_focus('header')

    def exit_path_mode(self) -> None:
        self.typing_mode = False
        self.footer.set_text(SELECTION_MODE_INSTRUCTIONS)
        self.header.set_edit_pos(len(self.header.get_edit_text()))
        self.view.set_focus('body')

    def handle_path_input(self) -> None:
        if not self.typing_mode:
            self.typing_mode = True
            self.footer.set_text(EDIT_MODE_INSTRUCTIONS)
            self.view.set_focus('header')
        path = Path(self.header.get_edit_text())
        if path.is_dir():
            self.current_dir = path
            self.walker[:] = self.get_directory_items()
            self.file_walker[:] = self.get_file_items()

    def keypress(self, size: tuple[int, int], key: str) -> str | None:  # noqa: PLR0911
        key = super().keypress(size, key)
        if self.typing_mode:
            if key == 'esc':
                self.exit_path_mode()
                self.header.keypress((len(self.header.get_edit_text()),), key)
                return None
            return key

        if key == 'backspace':
            self.change_directory(DirectoryButton('..'))
            return None
        if isinstance(key, str):
            if key.lower() == 'c':
                self.confirm_selection()
                return None
            if key.lower() == 'r':
                self.return_to_selection()
                return None
            if key.lower() == 't':
                self.enter_path_mode()
                return None

        return key
