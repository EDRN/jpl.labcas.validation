# encoding: utf-8

'''🛂 EDRN DICOM Validation: functions.'''

from .errors import DirectoryError
from .const import IGNORED_FILES
import re, os, pydicom

_event_id_re = re.compile(r'^\d{7}$')


def check_directory(target: str):
    '''Check that the target directory has the expected layout.

    This will raise a DirectoryError if the directory does not have the expected layout.

    The expected layout is:

    📁 target directory (such as Prostate_MRI)
    ├── 📁 site folder (such as Images_Site_qfP7OH9pjawWGA)
    │   ├── 📁 event folder (1644175)
    │   ├── 📁 event folder (1810893)
    │   …
    ├── 📁 site folder (such as Images_Site_uDUsCV9ikmtw)
    │   ├── 📁 event folder (1080030)
    │   ├── 📁 event folder (1816383)
    │   …
    …
    '''
    if not os.path.isdir(target):
        raise DirectoryError(f'📄 Target directory {target} is not a directory')
    sites = os.listdir(target)
    if not sites:
        raise DirectoryError(f'🫙 Target directory {target} is empty')
    for site in sites:
        if site in IGNORED_FILES: continue

        # Disabling this check as there are LOTS of things `like Prostate_MRI/Prostate_MRI.cfg` on
        # the LabCAS disk that it's not worth the headache
        # if not os.path.isdir(os.path.join(target, site)):
        #     raise DirectoryError(f'📄 Site {site} in target directory {target} is not a directory')
        #
        # events = os.listdir(os.path.join(target, site))
        # if not events:
        #     raise DirectoryError(f'🫙 Site {site} in target directory {target} is empty')
        #
        # for event in events:
        #     if event in IGNORED_FILES: continue
        #     if not os.path.isdir(os.path.join(target, site, event)):
        #         raise DirectoryError(f'📄 Event {event} in site {site} in target directory {target} is not a directory')
        #     if not _event_id_re.match(event):
        #         raise DirectoryError(f'❌ Unexpected format for event folder "{event}" in {target}/{site}')
    
    # Now ensure there's at least one DICOM file somewhere under the target directory
    for r, _, files in os.walk(target):
        for f in files:
            try:
                pydicom.dcmread(os.path.join(r, f), stop_before_pixels=False, force=False)
                return
            except (IOError, pydicom.errors.InvalidDicomError) as ex:
                continue
            except Exception as ex:
                raise DirectoryError(f'💥 Unexpected exception reading file {os.path.join(r, f)}: {ex}')
    raise DirectoryError(f'🫙 No valid DICOM files found in {target}')


def textify_dicom_value(value: any) -> list[str]:
    '''Textify the given value.
    
    Returns a list of string representations of text-representable values.
    Returns empty string for binary values or anything else that can't be represented as text.
    '''
    result: list[str] = []
    
    # Handle strings directly
    if isinstance(value, str):
        result.append(value)
    # Handle binary data by returning an empty string
    elif isinstance(value, (bytes, bytearray)):
        result.append('')
    # Handle sequences - recursively process each element and flatten
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            result.extend(textify_dicom_value(v))
    # Handle other types - try to convert to string if possible
    else:
        try:
            result.append(str(value))
        except Exception:
            # If conversion fails, return empty string
            result.append('')
    
    return result


def modality(ds: pydicom.Dataset) -> str:
    '''Determine the modality of the given DICOM dataset.'''
    if hasattr(ds, 'Modality'):
        modality = ds.Modality if ds.Modality is not None and ds.Modality.strip() != '' else 'UNKNOWN'
    else:
        modality = 'UNKNOWN'
    return modality
