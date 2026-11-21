"""Check that the supplied art exists before a teacher enables the game."""
from pathlib import Path
from django.conf import settings

BASE_FILES = (
    'sea-sky.png', 'sea-water-back.png', 'sea-water-front.png', 'player-deck.png',
    'sailor-back.png', 'cannon-base.png', 'cannon-barrel.png', 'cannonball.png',
    'commander-master.png', 'flag-covered-cloud.png', 'reference/choice-ship-master.png', 'choice-ship-pirate.png',
    'cloud-big-1.png', 'cloud-big-2.png', 'cloud-big-3.png', 'cloud-big-4.png',
)


def missing_game_assets():
    root = Path(settings.BASE_DIR) / 'static' / 'img' / 'game-tau-bien'
    return [name for name in BASE_FILES if not (root / name).is_file()]
