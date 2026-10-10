"""Output mapping and conservative filesystem safety checks."""
from pathlib import Path
from .models import Job, Layout, Photo, SafetyError

def within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents

def reject_links(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink() or (hasattr(component, 'is_junction') and component.is_junction()):
            raise SafetyError(f'Links/junctions are not allowed in output paths: {component}')

def make_layout(sources, output=None) -> Layout:
    roots = tuple(dict.fromkeys(Path(p).expanduser().resolve(strict=True) for p in sources))
    if not roots or any(not p.is_dir() for p in roots):
        raise SafetyError('Supply one or more existing source directories')
    if any(within(a, b) for a in roots for b in roots if a != b):
        raise SafetyError('Overlapping source directories are ambiguous; select non-overlapping roots')
    if output is None:
        if len({p.parent for p in roots}) != 1:
            raise SafetyError('Source directories have different parents; specify --output')
        raw = roots[0].parent / 'web'
    else:
        raw = Path(output).expanduser().absolute()
    reject_links(raw)
    dest = raw.resolve()
    if any(within(dest, r) or within(r, dest) for r in roots):
        raise SafetyError('Output must be separate from, and neither inside nor above, any source directory')
    # Recognize the conventional library when scanning a parent Photos directory.
    exclusions = tuple({dest, *(r / 'web' for r in roots)})
    return Layout(roots, dest, exclusions)

def map_photo(photo: Photo, layout: Layout) -> Job:
    return Job(photo, layout.output / photo.source_root.name / photo.relative_path.with_suffix('.jpg'))

def validate_job(job: Job, layout: Layout) -> None:
    raw = job.destination.absolute()
    reject_links(raw)
    dest = raw.resolve()
    if not within(dest, layout.output) or dest == layout.output:
        raise SafetyError(f'Destination escapes output library: {dest}')
    if any(within(dest, r) for r in layout.sources) or dest == job.photo.source.resolve():
        raise SafetyError(f'Destination could overwrite an original: {dest}')
    if dest.exists():
        if not dest.is_file() or dest.stat().st_nlink > 1:
            raise SafetyError(f'Output is not an ordinary unlinked file: {dest}')
        if job.photo.source.exists() and dest.samefile(job.photo.source):
            raise SafetyError(f'Output aliases source: {dest}')
    # Avoid case-only aliases of existing output names even on Linux.
    current = layout.output
    if current.exists() and not current.is_dir():
        raise SafetyError(f'Output root is not a directory: {current}')
    for part in raw.relative_to(layout.output).parts:
        if current.is_dir():
            aliases = [p for p in current.iterdir() if p.name.casefold() == part.casefold() and p.name != part]
            if aliases:
                raise SafetyError(f'Case-insensitive output alias: {aliases[0]} versus {part}')
        current = current / part
