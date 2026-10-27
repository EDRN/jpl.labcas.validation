# encoding: utf-8

'''🛂 EDRN DICOM Validation: extract burned-in text from DICOM image pixels.

Reads a single DICOM file and prints OCR text found in its pixel data to stdout.
Frame selection and Tesseract settings match the simple scoring PHI/PII recognizer.
'''

from __future__ import annotations

from PIL import Image
import argparse, logging, os, sys

import pydicom
import pytesseract

# Avoid problematic DICOM files so we can still grab as many of the tags and values as we can
pydicom.config.convert_wrong_length_to_UN = True

__doc__ = '🛂 Extract text from DICOM image pixels via Tesseract OCR'
_logger = logging.getLogger(__name__)


def _extract_frames(ds: pydicom.Dataset, max_frames: int = 4) -> list:
    '''Extract up to `max_frames` frames from the given DICOM dataset.

    Matches ``SimpleScoring_PHI_PII_Recognizer._extract_frames``.
    '''
    frames = []
    # The `pixel_array` is a `@property` which even if we just do `hasattr` can cause
    # a whole bunch of things to happen—and raise exceptions!
    if not hasattr(ds, 'pixel_array'): return frames

    try:
        # And then grab it:
        arr = ds.pixel_array  # This can raise a whole heapload of exceptions, so we just catch Exception below

        # Multi-frame DICOM have `ndim` (number dimensions)
        if getattr(arr, 'ndim', 0) == 3:
            # (frames, rows cols) or (rows, cols, channels)
            if arr.shape[0] > 8 and arr.shape[0] >= max_frames:
                # There could be hundreds of frames, so we get evenly spaced ones with a step size
                step = max(1, arr.shape[0] // max_frames)  ## step size with larger of 1 and floor division
                frame_indexes = list(range(0, arr.shape[0], step))[:max_frames]
                for i in frame_indexes:
                    if arr.shape[-1] in (3, 4):  # RGB(A)
                        frames.append(Image.fromarray(arr))
                        break
                    frames.append(Image.fromarray(arr[i]))
            else:
                if arr.shape[-1] in (3, 4):  # RGB(A)
                    frames.append(Image.fromarray(arr))
                else:
                    for i in range(min(max_frames, arr.shape[0])):
                        frames.append(Image.fromarray(arr[i]))
        elif getattr(arr, 'ndim', 0) == 2:
            # Single grayscale image
            frames.append(Image.fromarray(arr))
        else:
            # Some unexpected like a 1D array or a 4D hyperstack, so just _try_ to render it
            frames.append(Image.fromarray(arr))
    except Exception:
        _logger.exception('💥 Unexpected (but ignored) exception extracting frames from %s', ds.filename)

    # Normalize to 8-bit so we can do OCR
    normalized = []
    for f in frames:
        try:
            if f.mode not in ('L', 'RGB'):
                normalized.append(f.convert('L'))  # L = lumincance (grayscale)
            else:
                normalized.append(f)
        except Exception:
            continue

    # Whew
    return normalized[:max_frames]


def _recognize_characters(
    frame: Image.Image,
    *,
    frame_index: int = 0,
    image_dir: str | None = None,
    stem: str = 'frame',
) -> str:
    '''Recognize characters in the given frame using OCR.

    Matches ``SimpleScoring_PHI_PII_Recognizer._recognize_characters`` (text only).
    When `image_dir` is set, the OCR'd frame is also written as a PNG under that directory.
    '''
    if image_dir is not None:
        out_path = os.path.join(image_dir, f'{stem}-frame{frame_index}-raw.png')
        frame.save(out_path)
        print(f'Wrote {out_path}', file=sys.stderr)
    try:
        data = pytesseract.image_to_data(frame, output_type=pytesseract.Output.DICT)
        n = len(data.get('text', []))
        texts = []
        for i in range(n):
            txt = (data.get('text')[i] or '').strip()
            if not txt: continue
            texts.append(txt)
        return ''.join(texts)
    except Exception:
        try:
            return pytesseract.image_to_string(frame)
        except Exception:
            return ''


def _extract_text(path: str, *, generate_images: bool = False) -> list[str]:
    '''Return OCR text strings for up to four frames of the DICOM at `path`.'''
    if not os.path.isfile(path):
        raise FileNotFoundError(f'No such file: {path}')
    try:
        ds = pydicom.dcmread(path, force=False)
    except Exception as ex:
        raise ValueError(f'Could not read DICOM file {path}: {ex}') from ex
    frames = _extract_frames(ds)
    if not frames:
        raise ValueError(f'No pixel frames available in {path}')
    image_dir = (os.path.dirname(os.path.abspath(path)) or '.') if generate_images else None
    stem = os.path.splitext(os.path.basename(path))[0]
    results = []
    for idx, frame in enumerate(frames):
        text = _recognize_characters(
            frame, frame_index=idx, image_dir=image_dir, stem=stem,
        )
        if text:
            results.append(text)
    return results


def main():
    '''Entrypoint for extracting text from DICOM image pixels.'''
    parser = argparse.ArgumentParser(
        description='Extract burned-in text from a DICOM file\'s image pixels via Tesseract OCR.'
    )
    parser.add_argument(
        'dicom_file', type=str,
        help='Path to a single DICOM file on disk',
    )
    parser.add_argument(
        '-g', '--generate-images', action='store_true',
        help='Write each OCR\'d frame as a PNG next to the DICOM file',
    )
    args = parser.parse_args()
    try:
        texts = _extract_text(args.dicom_file, generate_images=args.generate_images)
    except Exception as ex:
        print(str(ex), file=sys.stderr)
        sys.exit(1)
    for text in texts:
        print(text)


if __name__ == '__main__':
    main()
