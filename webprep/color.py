"""ICC conversion and alpha compositing. Only the generated sRGB profile survives."""
from io import BytesIO
from PIL import Image, ImageCms

SRGB_PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
SRGB_BYTES = SRGB_PROFILE.tobytes()

class ColorError(ValueError):
    pass

def to_srgb(image: Image.Image, profile: bytes | None, background=(255, 255, 255)):
    warnings = []
    alpha = image.convert('RGBA').getchannel('A') if 'A' in image.getbands() or 'transparency' in image.info else None
    if image.mode in ('RGBA', 'P', 'PA'):
        pixels = image.convert('RGB')
    elif image.mode == 'LA':
        pixels = image.getchannel('L')
    elif image.mode in ('RGB', 'L', 'CMYK', 'LAB'):
        pixels = image
    elif image.mode.startswith('I') or image.mode == 'F':
        raise ColorError('High-bit-depth grayscale/float requires a deliberate tone mapping; conversion refused')
    else:
        pixels = image.convert('RGB')
    if profile:
        try:
            source = ImageCms.ImageCmsProfile(BytesIO(profile))
            rgb = ImageCms.profileToProfile(pixels, source, SRGB_PROFILE, outputMode='RGB')
        except (OSError, ValueError, ImageCms.PyCMSError) as exc:
            raise ColorError(f'ICC profile is malformed or incompatible: {exc}') from exc
    else:
        if pixels.mode == 'LAB':
            raise ColorError('Unprofiled LAB has no safe color interpretation')
        rgb = pixels.convert('RGB')
        warnings.append('No ICC profile: assuming sRGB for RGB/grayscale; unprofiled CMYK uses Pillow fallback')
    if alpha is not None:
        rgb = Image.composite(rgb, Image.new('RGB', rgb.size, background), alpha)
    return rgb, warnings
