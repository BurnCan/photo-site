"""Preflight all selected photographs before any writes; selection belongs to caller."""
from collections import defaultdict
from .models import Result
from .paths import map_photo, validate_job
from .processor import process_image

def process_batch(photos, layout, settings, *, overwrite=False, dry_run=False, on_result=None):
    jobs = [map_photo(p, layout) for p in photos]
    groups = defaultdict(list)
    for job in jobs:
        validate_job(job, layout)
        groups[str(job.destination).casefold()].append(job)
    results = []
    for job in jobs:
        conflicts = groups[str(job.destination).casefold()]
        if len(conflicts) > 1:
            result = Result(job, 'COLLISION', 'conflicting sources: ' + ', '.join(str(j.photo.source) for j in conflicts))
        else:
            result = process_image(job, layout, settings, overwrite=overwrite, dry_run=dry_run)
        results.append(result)
        if on_result:
            on_result(result)
    return results
