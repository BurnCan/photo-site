"""Decode read-only input, normalize pixels, and publish complete JPEGs atomically."""
import os
import tempfile
import warnings
from PIL import Image, ImageOps
from .color import ColorError, SRGB_BYTES, to_srgb
from .models import Job, Layout, Result, Settings
from .paths import validate_job

def resized_dimensions(dimensions: tuple[int, int], maximum: int) -> tuple[int, int]:
    if maximum < 1 or min(dimensions) < 1:
        raise ValueError('Dimensions and maximum must be positive')
    scale = min(1.0, maximum / max(dimensions))
    return tuple(max(1, round(d * scale)) for d in dimensions)

def process_image(job: Job, layout: Layout, settings=Settings(), *, overwrite=False, dry_run=False) -> Result:
    validate_job(job, layout)
    if job.destination.exists() and not overwrite:
        return Result(job, 'SKIPPED', 'output already exists')
    if dry_run:
        return Result(job, 'WOULD CREATE', 'would replace existing output' if job.destination.exists() else '')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with job.photo.source.open('rb') as source_file, Image.open(source_file) as image:
                image.load()
                original = image.size
                profile = image.info.get('icc_profile')
                oriented = ImageOps.exif_transpose(image)
                rgb, notices = to_srgb(oriented, profile, settings.background)
                if getattr(image, 'n_frames', 1) > 1:
                    notices.append('Multi-frame image: only the first frame is exported')
                dimensions = resized_dimensions(rgb.size, settings.size)
                if rgb.size != dimensions:
                    rgb = rgb.resize(dimensions, Image.Resampling.LANCZOS)
                # Construct a fresh image, discarding all decoder metadata, EXIF and comments.
                clean = Image.new('RGB', rgb.size)
                clean.paste(rgb)
    except (OSError, ValueError, ColorError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        return Result(job, 'ERROR', str(exc))
    validate_job(job, layout)
    job.destination.parent.mkdir(parents=True, exist_ok=True)
    validate_job(job, layout)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=job.destination.parent, prefix='.webprep-', suffix='.tmp', delete=False) as handle:
            temporary = handle.name
            clean.save(handle, format='JPEG', quality=settings.quality, optimize=True, icc_profile=SRGB_BYTES)
            handle.flush()
            os.fsync(handle.fileno())
        validate_job(job, layout)
        if overwrite:
            os.replace(temporary, job.destination)
            temporary = None
        else:
            try:
                # An atomic exclusive publication: an output appearing mid-run is never overwritten.
                os.link(temporary, job.destination)
            except FileExistsError:
                return Result(job, 'SKIPPED', 'output appeared during processing')
        return Result(job, 'CREATED', original_dimensions=original, output_dimensions=dimensions, warnings=notices)
    finally:
        if temporary is not None:
            os.unlink(temporary)
