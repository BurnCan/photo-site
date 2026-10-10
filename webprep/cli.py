"""CLI parsing and human-readable reporting."""
import argparse
from collections import Counter
from .models import DEFAULT_SIZE, SafetyError, Settings
from .paths import make_layout
from .scanner import scan_sources
from .batch import process_batch

def report(result):
    print(f'{result.status:12} {result.job.photo.source}\n             -> {result.job.destination}')
    if result.message:
        print(f'             {result.message}')
    for warning in result.warnings:
        print(f'             WARNING: {warning}')

def main(argv=None):
    parser = argparse.ArgumentParser(description='Create metadata-free sRGB web JPEGs without changing originals.',
        epilog='Example: python webprep.py "D:\\Photos\\Balloon Pop" "D:\\Photos\\Light Trails" --dry-run')
    parser.add_argument('sources', nargs='+', help='source directories (quote paths containing spaces)')
    parser.add_argument('--output', help='common output library; defaults to shared parent/web')
    parser.add_argument('--size', type=int, default=DEFAULT_SIZE, help=f'maximum long edge, 1–65535 pixels (default: {DEFAULT_SIZE})')
    parser.add_argument('--quality', type=int, default=82, help='JPEG quality, 1–95 (default: 82)')
    parser.add_argument('--overwrite', action='store_true', help='replace validated existing web copies')
    parser.add_argument('--dry-run', action='store_true', help='preflight and report without writing or decoding images')
    args = parser.parse_args(argv)
    try:
        settings = Settings(args.size, args.quality)
        layout = make_layout(args.sources, args.output)
        photos = scan_sources(layout)
        print(f'Output library: {layout.output}')
        results = process_batch(photos, layout, settings, overwrite=args.overwrite, dry_run=args.dry_run, on_result=report)
    except (SafetyError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}\nProcessing stopped. No further outputs will be written.')
        return 2
    counts = Counter(r.status for r in results)
    print('\nDry run complete — no files written.' if args.dry_run else '\nProcessing complete.')
    print(f'Source directories: {len(layout.sources)}\nImages discovered: {len(photos)}')
    for status in ('CREATED', 'WOULD CREATE', 'SKIPPED', 'COLLISION', 'ERROR'):
        print(f'{status.title()}: {counts[status]}')
    print(f'Output library: {layout.output}')
    return 1 if counts['ERROR'] or counts['COLLISION'] else 0
