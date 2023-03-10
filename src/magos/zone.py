from typing import Tuple


def get_zone_filenames(zone: int) -> Tuple[str, str]:
    return f'{zone:03d}1.VGA', f'{zone:03d}2.VGA'
