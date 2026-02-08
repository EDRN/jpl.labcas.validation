# encoding: utf-8

'''🛂 EDRN DICOM Validation: functions.'''

from .errors import DirectoryError
from .const import IGNORED_FILES, IGNORED_FOLDERS
from typing import Iterable
import re, os, pydicom, logging, os.path

_logger = logging.getLogger(__name__)
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
    for r, _, files in os.walk(target, followlinks=True):
        for f in files:
            candidate = os.path.join(r, f)
            try:
                pydicom.dcmread(candidate, stop_before_pixels=False, force=False)
                return
            except (IOError, pydicom.errors.InvalidDicomError) as ex:
                continue
            except Exception as ex:
                raise DirectoryError(f'💥 Unexpected exception reading file {candidate}: {ex}')
    raise DirectoryError(f'🫙 No valid DICOM files found in {target}')


def is_anonymized_value(s: str) -> bool:
    '''Check if a value should be considered anonymized and skipped.
    
    Returns True if the value:
    - Starts with "anon" (case-insensitive), OR
    - Matches "Doe John", "Doe^John", "John Doe", or "John^Doe" (case-insensitive), OR
    - Matches the specific anonymized value "P0HeLkT8KYKj14Q7GTGJjL^ry_x+LTzqsQgC9B5hZWso"
    '''
    if not s:
        return False
    s_stripped = s.strip()
    if not s_stripped:
        return False
    
    s_lower = s_stripped.lower()
    
    # Check if starts with "anon"
    if s_lower.startswith('anon'):
        return True
    
    # Check for specific anonymized value
    # Also handle trailing carets/spaces
    normalized = s_stripped.rstrip('^').strip()
    normalized_lower = normalized.lower()
    if normalized_lower == 'p0helkt8kykj14q7gtgjjl^ry_x+ltzqsqgc9b5hzwso':
        return True
    
    # Check for "Doe John" patterns (case-insensitive)
    # Match: "Doe John", "Doe^John", "John Doe", "John^Doe"
    # Also handle trailing carets/spaces and multiple carets
    
    # Check exact matches for common patterns
    if normalized_lower in ('doe john', 'john doe', 'doe^john', 'john^doe'):
        return True
    
    # Check if it matches the pattern with optional spaces/carets
    # Pattern: (Doe|John) followed by (space or ^) followed by (John|Doe)
    doe_john_pattern = re.compile(r'^(doe|john)[\s\^]+(john|doe)', re.IGNORECASE)
    if doe_john_pattern.match(normalized):
        return True
    
    return False


def textify_dicom_value(value: any) -> list[str]:
    '''Textify the given value.
    
    Returns a list of string representations of text-representable values.
    For binary values (bytes/bytearray), attempts to decode to text. If successful and under
    100 characters, returns the text. If 100+ characters, truncates to 100 and adds ellipsis.
    Returns empty string for binary values that can't be decoded or anything else that can't be represented as text.
    '''
    result: list[str] = []
    
    # Handle strings directly
    if isinstance(value, str):
        result.append(value)
    # Handle binary data - attempt to decode to text
    elif isinstance(value, (bytes, bytearray)):
        try:
            decoded_text = value.decode('utf-8', errors='replace')
            if len(decoded_text) < 100:
                result.append(decoded_text)
            else:
                result.append(decoded_text[:100] + '…')
        except Exception as ex:
            _logger.warning(f'Failed to decode binary DICOM value to text: {ex}')
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



def iterate_paths(root: str) -> Iterable[str]:
    '''Iterate over the paths in the given directory.

    We can't assume DICOM files end in .dcm; a lot of them come in without extensions, so process every file.
    '''
    for r, _, files in os.walk(root, followlinks=True):
        dirname = os.path.basename(r)
        if dirname in IGNORED_FOLDERS: continue
        for f in files:
            if f in IGNORED_FILES: continue
            file_to_yield = os.path.join(r, f)
            yield file_to_yield
