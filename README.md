# WebPrep — Photo Web Downscaler V1

WebPrep creates reduced-resolution web JPEGs from immutable master photographs.
WebPrep includes a desktop GUI, CLI, and reusable processing library. It does not
include thumbnails, a database, Instagram integration, authentication, or publishing.

## Setup

Requires Python **3.12 or newer**. Runtime dependency: Pillow (including ImageCms).
pytest is included for verification. Install [Git](https://git-scm.com/downloads)
if it is not already available, then clone the repository and enter its directory:

```bash
git clone https://github.com/BurnCan/photo-site.git
cd photo-site
```

Run the remaining setup and usage commands from the `photo-site` directory.
Create an isolated Python environment:

```bash
python -m venv .venv
```

Windows activation:

```bat
.venv\Scripts\activate
```

macOS/Linux activation:

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
python -m pytest -q
```

## Desktop GUI

Launch from the project directory with the virtual environment active:

```bash
python -m webprep.gui
```

Add one or more source folders, choose an output folder (or leave it blank for
`<shared parent>/web`), and set the maximum edge and JPEG quality. **Preview**
validates and lists planned changes without writing files. **Process images**
creates the web copies. Existing outputs are skipped unless overwrite is enabled;
replacing them requires confirmation. Progress, warnings, errors, and a summary
appear in the window. Processing runs in a background thread so the window stays
responsive. Wait for the batch to finish before closing the window.

Tkinter is included with standard Windows Python. On Ubuntu/WSL, install it with:

```bash
sudo apt install python3-tk
```

WSL needs WSLg GUI support (available on supported Windows 10/11 installations).
Launch from Ubuntu, and use Linux paths such as `/mnt/c/Users/weird/Desktop/Images`.
The same source/output safety rules and image processing behavior apply to both
interfaces. Source folders and the output folder must not contain one another.

## Usage

```text
python webprep.py SOURCE [SOURCE ...] [--output DIRECTORY]
                  [--size PIXELS] [--quality QUALITY] [--overwrite] [--dry-run]
```

```bat
python webprep.py "D:\Photos\Balloon Pop" --dry-run
python webprep.py "D:\Photos\Balloon Pop"
python webprep.py "D:\Photos\Balloon Pop" "D:\Photos\Light Trails"
python webprep.py "D:\Photos\Balloon Pop" --output "D:\Photos\web" --size 1600 --quality 85
python webprep.py "D:\Photos\Balloon Pop" --overwrite
python webprep.py --help
```

`python -m webprep` is also supported. Quote paths with spaces.
Sources sharing an immediate parent default to `<parent>/web`. Sources with different
parents require `--output`; WebPrep will not guess a location.

The scanner recognizes JPG, JPEG, PNG, TIF and TIFF, case-insensitively, recursively.
Unsupported files are ignored. Each source gets its own folder; relative subfolders
and filename stems are preserved:

```text
Photos/
    Balloon Pop/Roll 1/scan001.tif
    Light Trails/image2.jpg
    web/
        Balloon Pop/Roll 1/scan001.jpg
        Light Trails/image2.jpg
```

No `_web` suffix is added. Existing outputs are `SKIPPED` unless `--overwrite` is
supplied. Collisions (including case-insensitive collisions) report every conflicting
source as `COLLISION`; none of the conflicting images is written. Counts in the summary
count affected images, not collision groups. Unrelated images can still be processed.
`--dry-run` validates paths, scans, detects collisions and reports planned changes
without creating directories/files or decoding images. It cannot diagnose corrupt
image data or ICC profiles until actual processing.

## Image processing

Defaults: **2048-pixel maximum long edge, JPEG quality 82, sRGB**. Aspect ratios are
preserved using Lanczos downsampling; small images are never upscaled. Size accepts
1–65535; quality accepts 1–95. EXIF orientation is applied before resizing.

Valid embedded ICC profiles are transformed to sRGB using ImageCms, rather than
merely relabeled. Unprofiled RGB and grayscale are assumed to be sRGB; unprofiled
CMYK uses Pillow's approximate conversion and reports a warning. Malformed or
incompatible profiles cause a per-image `ERROR` and do not interrupt other images.
Alpha is preserved through color conversion then composited over white. The
background is configurable through the library's `Settings` model.

Outputs are fresh RGB JPEGs: original EXIF, GPS, serial numbers, dates, comments,
XMP and thumbnails are not copied. Only the generated standard sRGB ICC profile
and normal JPEG display headers are retained. Originals retain all their metadata.

## Safety

Sources are opened only in binary read mode. WebPrep never renames, removes, moves,
or writes source files. Output paths are canonicalized and validated before writing.
For conservative V1 behavior, an output root cannot be equal to, inside, or above a
selected source root. Select sibling shoot folders when choosing a library inside
`Photos`. Overlapping selected source roots are rejected.

The actual output root is excluded from discovery. When scanning a parent `Photos`
folder, its resolved conventional `Photos/web` library is also excluded; other
nested directories called `web` are retained. Source file/directory symlinks and
junction directories are not followed. Output path symlinks/junctions, hardlinked
existing outputs and case-only aliases are refused. These checks also apply with
`--overwrite`, including direct calls to the processing library.

JPEGs are encoded to a unique temporary file inside the output folder. Without
`--overwrite`, an atomic hard-link operation publishes the completed image only
if the destination does not already exist. With `--overwrite`, atomic replacement
publishes it. Temporary files are cleaned up; stale web copies are never deleted.
Unexpected filesystem errors stop the batch. Decode/color failures are per-file.
Exit codes: 0 success (including skips), 1 image errors/collisions, 2 configuration
or filesystem safety failure.

## Library architecture

`models.py` supplies structured photos, jobs, results and settings; `scanner.py`
performs discovery; `paths.py` maps outputs and checks safety; `color.py` manages
ICC and transparency; `processor.py` converts a single image; `batch.py` preflights
selected photos and reports results through an optional callback. `cli.py` handles
argument parsing and presentation. The core has no CLI dependency.

```python
from webprep import make_layout, scan_sources, process_batch, Settings
layout = make_layout(["D:/Photos/Balloon Pop"])
photos = scan_sources(layout)
results = process_batch(photos[:10], layout, Settings(), dry_run=True)
```

`gui.py` uses the same batch API and sends progress events to the Tk event loop
through a queue; the processing library has no GUI dependency.

## Limitations

Reduced resolution discourages large high-quality prints; it is not copy protection.
Only the first frame/page of multi-frame images is exported, with a warning.
High-bit-depth grayscale/float TIFFs and unprofiled LAB are refused because safe tone
mapping/color interpretation needs an explicit policy. RGB TIFF support depends on
Pillow's decoder; specialized scan formats may require future tooling. Very large
images trigger Pillow's decompression-bomb protection. Processing decodes one full
image at a time and can use substantial memory.

Atomic exclusive publication requires a filesystem supporting hard links; unsupported
filesystems fail safely. Do not run concurrent writers or let another process change
output directories during a run: portable pathname checks cannot guarantee protection
against hostile directory substitution between validation and publication. Ordinary
source reads can update access times at the OS/filesystem level; WebPrep does not
intentionally change source timestamps. Backups and OS read-only permissions provide
additional protection for irreplaceable masters.

Tests cover transformations, metadata and orientation pixels, modes and profiles,
collisions, corrupt files, path/link safety, hash/size/mtime integrity, dry runs, and
an end-to-end temporary two-shoot CLI workflow. Generated libraries are intentionally
not globally ignored in `.gitignore`; keep real photographs outside this code project.
