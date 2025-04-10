from dataclasses import dataclass
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from magos.agos_opcode import (
    elvira2_ops,
    elvira_ops,
    feeble_ops,
    puzzlepack_ops,
    simon2_ops,
    simon2_ops_talkie,
    simon_ops,
    simon_ops_talkie,
    waxworks_ops,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from magos.stream import FilePath


@total_ordering
class GameID(Enum):
    elvira1 = 'Elvira: Mistress of the Dark'
    elvira2 = 'Elvira II: The Jaws of Cerberus'
    waxworks = 'Waxworks'
    simon1 = 'Simon the Sorcerer'
    simon2 = 'Simon the Sorcerer II: The Lion, the Wizard and the Wardrobe'
    feeble = 'The Feeble Files'
    puzzle = "Simon the Sorcerer's Puzzle Pack"

    @property
    def version(self) -> int:
        return tuple(GameID).index(self)

    def __hash__(self) -> int:
        return self.version

    def __lt__(self, value: 'GameID') -> bool:
        return self.version < value.version


@dataclass(frozen=True)
class DetectionEntry:
    name: str
    variant: str | None
    game: GameID
    script: str
    basefile: str
    archive: str | None = None

    def __str__(self) -> str:
        version_info = ' '
        if self.variant:
            version_info = f': {self.variant} '
        return f'{self.game.value}{version_info}[{self.name}]'


optables = {
    GameID.elvira1: {
        'floppy': elvira_ops,
    },
    GameID.elvira2: {
        'floppy': elvira2_ops,
    },
    GameID.puzzle: {
        'floppy': puzzlepack_ops,
    },
    GameID.waxworks: {
        'floppy': waxworks_ops,
    },
    GameID.simon1: {
        'floppy': simon_ops,
        'talkie': simon_ops_talkie,
    },
    GameID.simon2: {
        'floppy': simon2_ops,
        'talkie': simon2_ops_talkie,
    },
    GameID.feeble: {
        'talkie': feeble_ops,
    },
}


DetectionMap: TypeAlias = 'DetectionEntry | Mapping[str, DetectionMap]'


class GameNotDetectedError(ValueError):
    def __init__(self, directory: str) -> None:
        super().__init__(
            f'Could not detect an AGOS game in the directory: {directory}\n'
            'Please ensure that the directory contains the necessary game files.\n'
            'Supported AGOS games:\n'
            + '\n'.join(f'\t- {game.value}' for game in GameID),
        )


def detect_files(
    basedir: 'FilePath',
    mapping: 'Mapping[str, DetectionMap]',
) -> DetectionEntry:
    res = None
    for basefile, option in mapping.items():
        if basefile == '_' or (Path(basedir) / basefile).exists():
            res = option
            break
    if res is None:
        raise GameNotDetectedError(str(basedir))
    assert res is not None
    if isinstance(res, dict):
        return detect_files(basedir, res)
    assert isinstance(res, DetectionEntry)
    return res


known_variants = {
    'elvira1': DetectionEntry(
        'elvira1',
        None,
        GameID.elvira1,
        'floppy',
        'GAMEPC',
    ),
    'elvira2': DetectionEntry(
        'elvira2',
        None,
        GameID.elvira2,
        'floppy',
        'GAMEPC',
    ),
    'waxworks-demo': DetectionEntry(
        'waxworks-demo',
        'Demo',
        GameID.waxworks,
        'floppy',
        'DEMO',
    ),
    'waxworks': DetectionEntry(
        'waxworks',
        None,
        GameID.waxworks,
        'floppy',
        'GAMEPC',
    ),
    'simon1-demo': DetectionEntry(
        'simon1-demo',
        'Demo',
        GameID.simon1,
        'floppy',
        'GDEMO',
    ),
    'simon1': DetectionEntry(
        'simon1',
        'Floppy version',
        GameID.simon1,
        'floppy',
        'GAMEPC',
    ),
    'simon1-talkie': DetectionEntry(
        'simon1-talkie',
        'Talkie version',
        GameID.simon1,
        'talkie',
        'GAMEPC',
        'SIMON.GME',
    ),
    'simon2': DetectionEntry(
        'simon2',
        'Floppy version',
        GameID.simon2,
        'floppy',
        'GAME32',
        'SIMON2.GME',
    ),
    'simon2-talkie': DetectionEntry(
        'simon2-talkie',
        'Talkie version',
        GameID.simon2,
        'talkie',
        'GSPTR30',
        'SIMON2.GME',
    ),
    'feeble': DetectionEntry(
        'feeble',
        None,
        GameID.feeble,
        'talkie',
        'GAME22',
    ),
    'dimp': DetectionEntry(
        'dimp',
        'Demon In My Pocket',
        GameID.puzzle,
        'floppy',
        'GDIMP',
    ),
    'jumble': DetectionEntry(
        'jumble',
        'Jumble',
        GameID.puzzle,
        'floppy',
        'GJUMBLE',
    ),
    'swampy': DetectionEntry(
        'swampy',
        'Swampy Adventures',
        GameID.puzzle,
        'floppy',
        'GSWAMPY',
    ),
    'puzzle': DetectionEntry(
        'puzzle',
        'NoPatience',
        GameID.puzzle,
        'floppy',
        'GPUZZLE',
    ),
}


def auto_detect_game_from_filenames(basedir: 'FilePath') -> DetectionEntry:
    basedir = Path(basedir)
    return detect_files(
        basedir,
        {
            'SIMON2.GME': {
                'GAME32': known_variants['simon2'],
                'GSPTR30': known_variants['simon2-talkie'],
            },
            'GAME22': known_variants['feeble'],
            'GAMEPC': {
                'SIMON.GME': known_variants['simon1-talkie'],
                'XTBLLIST': known_variants['waxworks'],
                'START': {
                    'STRIPPED.TXT': known_variants['elvira2'],
                    '_': known_variants['elvira1'],
                },
                '_': known_variants['simon1'],
            },
            'GDEMO': known_variants['simon1-demo'],
            'DEMO': known_variants['waxworks-demo'],
            'GJUMBLE': known_variants['jumble'],
            'GDIMP': known_variants['dimp'],
            'GSWAMPY': known_variants['swampy'],
            'GPUZZLE': known_variants['puzzle'],
        },
    )
