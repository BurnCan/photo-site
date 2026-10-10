"""Verify the GUI worker uses the real processing pipeline and reports outcomes."""
from queue import Queue

from PIL import Image

from webprep import Settings
from webprep.gui import run_batch


def drain(events):
    result = []
    while not events.empty():
        result.append(events.get_nowait())
    return result


def test_worker_creates_resized_image_and_reports_progress(tmp_path):
    source = tmp_path / 'roll'
    source.mkdir()
    Image.new('RGB', (100, 50), 'red').save(source / 'photo.png')
    events = Queue()
    run_batch([str(source)], str(tmp_path / 'web'), Settings(40, 85), False, False, events)
    messages = drain(events)
    assert [kind for kind, _ in messages] == ['scanned', 'result', 'done']
    assert messages[1][1].status == 'CREATED'
    assert messages[-1][1][0]['CREATED'] == 1
    with Image.open(tmp_path / 'web' / 'roll' / 'photo.jpg') as image:
        assert image.size == (40, 20)
    assert (source / 'photo.png').exists()


def test_worker_preview_writes_nothing(tmp_path):
    source = tmp_path / 'roll'
    source.mkdir()
    Image.new('RGB', (10, 10)).save(source / 'photo.png')
    events = Queue()
    run_batch([str(source)], str(tmp_path / 'web'), Settings(), False, True, events)
    messages = drain(events)
    assert messages[1][1].status == 'WOULD CREATE'
    assert messages[-1][1][1] is True
    assert not (tmp_path / 'web').exists()


def test_worker_reports_unsafe_output_without_writing(tmp_path):
    source = tmp_path / 'roll'
    source.mkdir()
    events = Queue()
    run_batch([str(source)], str(source / 'web'), Settings(), False, False, events)
    messages = drain(events)
    assert len(messages) == 1
    assert messages[0][0] == 'error'
    assert not (source / 'web').exists()
