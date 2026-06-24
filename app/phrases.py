import random
from pathlib import Path

PHRASES_FILE = Path(__file__).with_name("phrases.txt")
KNOWN_SECTIONS = {"add", "stat"}


def load_phrases() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {section: [] for section in KNOWN_SECTIONS}
    try:
        lines = PHRASES_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {section: () for section in KNOWN_SECTIONS}

    current_section: str | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            candidate = line[1:-1].strip().lower()
            current_section = candidate if candidate in KNOWN_SECTIONS else None
            continue
        if current_section is not None:
            result[current_section].append(line)
    return {section: tuple(values) for section, values in result.items()}


def random_phrase(section: str) -> str:
    phrases = load_phrases().get(section, ())
    return random.choice(phrases) if phrases else ""
