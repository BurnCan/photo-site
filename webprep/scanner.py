"""Read-only discovery; no image decoding or output creation."""
import os
from pathlib import Path
from .models import Layout, Photo, SUPPORTED_EXTENSIONS
from .paths import within

def scan_sources(layout: Layout) -> list[Photo]:
    photos = []
    excluded = tuple(p.resolve() for p in layout.exclusions)
    def scan_error(error):
        raise error
    for root in layout.sources:
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=scan_error):
            base = Path(directory)
            dirs[:] = sorted(d for d in dirs if not (base / d).is_symlink()
                             and not (hasattr(base / d, 'is_junction') and (base / d).is_junction())
                             and not any(within((base / d).resolve(), e) for e in excluded))
            for name in sorted(files):
                path = base / name
                if path.suffix.lower() in SUPPORTED_EXTENSIONS and path.is_file() and not path.is_symlink():
                    photos.append(Photo(path, root, path.relative_to(root)))
    return photos
