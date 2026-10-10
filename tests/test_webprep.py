import hashlib
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import pytest
from PIL import Image, ImageCms
from webprep import Settings, SafetyError, Job, make_layout, scan_sources, map_photo, process_image, process_batch


def photo(path, mode='RGB', size=(80, 40), color=None, **save):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path, **save)
    return path


def run(root, **kwargs):
    layout = make_layout([root])
    return process_batch(scan_sources(layout), layout, Settings(size=32), **kwargs)


@pytest.mark.parametrize('size,expected', [((6000,4000),(1600,1067)), ((4000,6000),(1067,1600)),
    ((3000,3000),(1600,1600)), ((1600,1000),(1600,1000)), ((10000,1),(1600,1))])
def test_resize(tmp_path, size, expected):
    root = tmp_path/'shoot'
    photo(root/'x.png', size=size)
    layout = make_layout([root])
    result = process_image(map_photo(scan_sources(layout)[0], layout), layout)
    assert result.status == 'CREATED'
    with Image.open(result.job.destination) as image:
        assert image.size == expected


def test_scan_mapping_and_exclusion(tmp_path):
    root = tmp_path/'Photos'
    photo(root/'Balloon Pop'/'Roll 1'/'X.TIF')
    photo(root/'web'/'old.jpg')
    photo(root/'archive'/'web'/'real.PNG')
    (root/'ignored.txt').write_text('hello')
    layout = make_layout([root])
    found = scan_sources(layout)
    assert len(found) == 2
    assert {p.relative_path.as_posix() for p in found} == {'Balloon Pop/Roll 1/X.TIF', 'archive/web/real.PNG'}
    assert map_photo(found[0], layout).destination == tmp_path/'web'/'Photos'/'Balloon Pop'/'Roll 1'/'X.jpg'


def test_multiple_and_explicit(tmp_path):
    a = photo(tmp_path/'A shoot'/'x.JPG').parent
    b = photo(tmp_path/'B shoot'/'nested'/'y.Jpeg').parent.parent
    layout = make_layout([a,b], tmp_path/'custom library')
    assert len(scan_sources(layout)) == 2
    assert {map_photo(p,layout).destination.relative_to(layout.output).as_posix() for p in scan_sources(layout)} == {'A shoot/x.jpg','B shoot/nested/y.jpg'}


@pytest.mark.parametrize('relation', ['same','inside','ancestor'])
def test_unsafe_layout(tmp_path, relation):
    root = tmp_path/'photos'; root.mkdir()
    output = {'same':root,'inside':root/'output','ancestor':tmp_path}[relation]
    with pytest.raises(SafetyError):
        make_layout([root], output)


def test_different_parents(tmp_path):
    a=tmp_path/'a'/'shoot'; b=tmp_path/'b'/'shoot'
    a.mkdir(parents=True); b.mkdir(parents=True)
    with pytest.raises(SafetyError, match='--output'):
        make_layout([a,b])


@pytest.mark.parametrize('names', [('photo.jpg','photo.tif'), ('Photo.jpg','photo.PNG')])
def test_collisions(tmp_path,names):
    root=tmp_path/'shoot'
    for name in names: photo(root/name)
    results=run(root,overwrite=True)
    assert [r.status for r in results] == ['COLLISION','COLLISION']
    assert not (tmp_path/'web').exists()


def test_same_source_names(tmp_path):
    a=photo(tmp_path/'a'/'shoot'/'x.jpg').parent
    b=photo(tmp_path/'b'/'shoot'/'x.tif').parent
    layout=make_layout([a,b],tmp_path/'out')
    assert all(r.status=='COLLISION' for r in process_batch(scan_sources(layout),layout,Settings()))


@pytest.mark.parametrize('mode,ext,color', [('RGB','png',(100,20,30)),('L','png',100),('RGBA','png',(0,0,0,0)),('LA','png',(0,0)),('CMYK','tif',(0,255,255,0)),('P','png',0)])
def test_modes(tmp_path,mode,ext,color):
    root=tmp_path/'shoot'; photo(root/f'x.{ext}',mode,color=color)
    result=run(root)[0]
    assert result.status=='CREATED'
    with Image.open(result.job.destination) as image:
        assert image.mode=='RGB'
        assert image.info['icc_profile']
        if mode in ('RGBA','LA'):
            assert min(image.getpixel((0,0))) >= 250


def test_metadata_orientation_pixels(tmp_path):
    root=tmp_path/'shoot'; root.mkdir()
    image=Image.new('RGB',(40,20),'red')
    image.paste('blue',(20,0,40,20))
    exif=Image.Exif(); exif[274]=6; exif[271]='Private Camera'; exif[306]='2000:01:01 00:00:00'
    image.save(root/'x.jpg',exif=exif,quality=95,comment=b'private')
    result=run(root)[0]
    with Image.open(result.job.destination) as output:
        assert output.size==(16,32)
        assert not output.getexif()
        assert 'comment' not in output.info
        top=output.getpixel((8,5)); bottom=output.getpixel((8,27))
        assert top[0]>200 and bottom[2]>200


@pytest.mark.parametrize('profile', [ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes(),b'broken ICC'])
def test_icc(tmp_path,profile):
    root=tmp_path/'shoot'; photo(root/'x.png',icc_profile=profile)
    result=run(root)[0]
    assert result.status == ('ERROR' if profile==b'broken ICC' else 'CREATED')


def test_lab_conversion(tmp_path):
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('LAB')).tobytes()
    root=tmp_path/'shoot'; photo(root/'x.tif',mode='LAB',color=(128,128,128),icc_profile=profile)
    assert run(root)[0].status=='CREATED'


@pytest.mark.parametrize('extension',['jpg','tif','png'])
def test_bad_file_continues(tmp_path,extension):
    root=tmp_path/'shoot'; photo(root/'good.jpg')
    (root/f'bad.{extension}').write_bytes(b'not an image')
    assert sorted(r.status for r in run(root))==['CREATED','ERROR']


def snapshot(root):
    return {p.relative_to(root).as_posix():(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_size,p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('extension',['jpg','tif','png'])
def test_source_integrity_skip_overwrite_dry(tmp_path,extension):
    root=tmp_path/'shoot'; source=photo(root/f'x.{extension}')
    before=snapshot(root)
    assert run(root)[0].status=='CREATED'
    output=tmp_path/'web'/'shoot'/'x.jpg'
    original_output=output.read_bytes()
    assert run(root)[0].status=='SKIPPED'
    assert output.read_bytes()==original_output
    assert run(root,overwrite=True)[0].status=='CREATED'
    whole=snapshot(tmp_path)
    assert run(root,dry_run=True,overwrite=True)[0].status=='WOULD CREATE'
    assert snapshot(tmp_path)==whole
    assert snapshot(root)==before


def test_dry_run_no_directories(tmp_path):
    root=tmp_path/'shoot'; photo(root/'x.jpg')
    before=snapshot(tmp_path)
    assert run(root,dry_run=True)[0].status=='WOULD CREATE'
    assert snapshot(tmp_path)==before
    assert not (tmp_path/'web').exists()


@pytest.mark.parametrize('kind',['file_symlink','directory_symlink','hardlink','direct_source','escape'])
def test_never_write_through_source(tmp_path,kind):
    root=tmp_path/'shoot'; source=photo(root/'x.jpg')
    layout=make_layout([root]); entry=scan_sources(layout)[0]; job=map_photo(entry,layout)
    before=snapshot(root)
    if kind=='file_symlink':
        job.destination.parent.mkdir(parents=True); job.destination.symlink_to(source)
    elif kind=='directory_symlink':
        layout.output.mkdir(); (layout.output/'shoot').symlink_to(root,target_is_directory=True)
    elif kind=='hardlink':
        job.destination.parent.mkdir(parents=True); os.link(source,job.destination)
    elif kind=='direct_source': job=Job(entry,source)
    else: job=Job(entry,tmp_path/'escaped.jpg')
    with pytest.raises(SafetyError): process_image(job,layout,overwrite=True)
    assert snapshot(root)==before


def test_output_root_symlink(tmp_path):
    root=tmp_path/'shoot'; root.mkdir()
    link=tmp_path/'link'; link.symlink_to(root,target_is_directory=True)
    with pytest.raises(SafetyError): make_layout([root],link)


def test_case_existing_alias(tmp_path):
    root=tmp_path/'shoot'; photo(root/'x.jpg')
    photo(tmp_path/'web'/'shoot'/'X.jpg')
    with pytest.raises(SafetyError): run(root,overwrite=True)


@pytest.mark.parametrize('size,quality',[(0,82),(-1,82),(65536,82),(2048,0),(2048,96)])
def test_invalid_settings(size,quality):
    with pytest.raises(ValueError): Settings(size,quality)


def test_cli_integration(tmp_path):
    photos=tmp_path/'Photos'
    a=photo(photos/'Balloon Pop'/'image1.tif').parent
    photo(a/'image2.jpg')
    b=photo(photos/'Light Trails'/'image3.tif').parent
    before={a:snapshot(a),b:snapshot(b)}
    script=Path(__file__).resolve().parents[1]/'webprep.py'
    def cli(*args):
        result=subprocess.run([sys.executable,str(script),str(a),str(b),*args],capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
        return result.stdout
    assert 'Created: 3' in cli()
    assert {p.relative_to(photos/'web').as_posix() for p in (photos/'web').rglob('*.jpg')} == {'Balloon Pop/image1.jpg','Balloon Pop/image2.jpg','Light Trails/image3.jpg'}
    assert 'Skipped: 3' in cli()
    all_before=snapshot(photos)
    assert 'no files written' in cli('--dry-run','--overwrite')
    assert snapshot(photos)==all_before
    assert all(snapshot(root)==state for root,state in before.items())


def test_failed_encoding_preserves_existing(tmp_path,monkeypatch):
    root=tmp_path/'shoot'; photo(root/'x.jpg')
    run(root)
    output=tmp_path/'web'/'shoot'/'x.jpg'; before=output.read_bytes()
    def fail(*args,**kwargs): raise OSError('simulated encoder failure')
    monkeypatch.setattr(Image.Image,'save',fail)
    with pytest.raises(OSError): run(root,overwrite=True)
    assert output.read_bytes()==before
    assert not list(output.parent.glob('.webprep-*'))


def test_exclusive_publication_race(tmp_path,monkeypatch):
    root=tmp_path/'shoot'; photo(root/'x.jpg')
    real_link=os.link
    def appeared(src,dst):
        Path(dst).write_bytes(b'other writer output')
        return real_link(src,dst)
    monkeypatch.setattr(os,'link',appeared)
    assert run(root)[0].status=='SKIPPED'
    output=tmp_path/'web'/'shoot'/'x.jpg'
    assert output.read_bytes()==b'other writer output'
    assert not list(output.parent.glob('.webprep-*'))


@pytest.mark.parametrize('mode,color', [('RGB', (100,20,30)), ('L', 100), ('RGBA', (10,20,30,128)), ('LA', (100,128)), ('P', 0)])
def test_default_srgb_profile_without_warning(tmp_path, mode, color):
    root = tmp_path / 'shoot'
    photo(root / 'x.png', mode=mode, color=color)
    result = run(root)[0]
    assert result.status == 'CREATED'
    assert result.warnings == []
    with Image.open(result.job.destination) as image:
        profile = ImageCms.ImageCmsProfile(BytesIO(image.info['icc_profile']))
        assert 'sRGB' in ImageCms.getProfileDescription(profile)


def test_unprofiled_cmyk_retains_specific_warning(tmp_path):
    root = tmp_path / 'shoot'
    photo(root / 'x.tif', mode='CMYK', color=(0,255,255,0))
    result = run(root)[0]
    assert result.status == 'CREATED'
    assert result.warnings == ['No CMYK ICC profile: using Pillow approximate conversion to sRGB']
