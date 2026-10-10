"""Models shared by the CLI and future user interfaces."""
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SIZE = 2048
DEFAULT_QUALITY = 82
SUPPORTED_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.tif', '.tiff'})

class SafetyError(ValueError):
    """An ambiguous or unsafe filesystem relationship."""

@dataclass(frozen=True)
class Settings:
    size: int = DEFAULT_SIZE
    quality: int = DEFAULT_QUALITY
    background: tuple[int, int, int] = (255, 255, 255)

    def __post_init__(self):
        if not 1 <= self.size <= 65535:
            raise ValueError('size must be an integer between 1 and 65535')
        if not 1 <= self.quality <= 95:
            raise ValueError('quality must be an integer between 1 and 95')
        if len(self.background) != 3 or any(not 0 <= c <= 255 for c in self.background):
            raise ValueError('background must contain three values between 0 and 255')

@dataclass(frozen=True)
class Photo:
    source: Path
    source_root: Path
    relative_path: Path

@dataclass(frozen=True)
class Layout:
    sources: tuple[Path, ...]
    output: Path
    exclusions: tuple[Path, ...]

@dataclass(frozen=True)
class Job:
    photo: Photo
    destination: Path

@dataclass
class Result:
    job: Job
    status: str
    message: str = ''
    original_dimensions: tuple[int, int] | None = None
    output_dimensions: tuple[int, int] | None = None
    warnings: list[str] = field(default_factory=list)
