# encoding: utf-8

'''🛂 EDRN DICOM Validation: files.'''

from dataclasses import dataclass
from functools import lru_cache
import pydicom, re, os.path, logging
from pydicom import datadict

_logger = logging.getLogger(__name__)


@dataclass
class PotentialFile:
    '''A file that we will scan for PHI/PII and check for compliance with EDRN validation requirements.'''
    path: str           # Relative path of the file
    site_id: str        # Blinded site ID
    event_id: str       # Event ID
    file_name: str      # File name

    # Regex for parsing organization parts from file paths
    _organization_re = re.compile(r'([^/]+)/(\d{7})/(.+)$')  # blah/blah/Images_site_XYX/1234567/f1/f2/…/file.dcm

    def __init__(self, path: str, site_id: str = None, event_id: str = None):
        '''Initialize the potential file with the given file path and optional site and event IDs.'''
        self.path = path

        search_result = self._organization_re.search(path)
        if search_result:
            self.site_id, self.event_id, self.file_name = search_result.groups()
        else:
            self.site_id, self.event_id, self.file_name = '«unknown site»', '«unknown event»', os.path.basename(path)

        if site_id: self.site_id = site_id
        if event_id: self.event_id = event_id

        # Produce this on demand
        self._profile_name = None

    @lru_cache
    def _read_dicom_file(self, stop_before_pixels: bool = False, force: bool = False) -> pydicom.Dataset:
        '''Read the DICOM file and return a dataset.'''
        return pydicom.dcmread(self.path, stop_before_pixels=stop_before_pixels, force=force)

    def dcmread(self, stop_before_pixels: bool = False, force: bool = False, cache: bool = True) -> pydicom.Dataset:
        '''Read the DICOM file and return a dataset.'''

        if cache:
            return self._read_dicom_file(stop_before_pixels, force)
        else:
            return pydicom.dcmread(self.path, stop_before_pixels=stop_before_pixels, force=force)

    def _safely_extract_value_for_tag(self, ds: pydicom.Dataset, tag_name: str) -> str | list[str] | None:
        '''Safely extract a value for a DICOM tag.
        
        Returns:
            - str: For single-value tags (e.g., SOPClassUID)
            - list[str]: For multi-value tags (e.g., ImageType with backslash-separated values or sequences)
            - None: If the tag doesn't exist or extraction fails
        '''
        try:
            # Convert tag name to tag number for more reliable access
            tag = datadict.tag_for_keyword(tag_name)
            if tag is None:
                # Fallback to getattr if keyword lookup fails
                tag_value = getattr(ds, tag_name, None)
                if tag_value is None:
                    return None
                # Extract the actual value - handle DataElement vs direct value
                if hasattr(tag_value, 'value'):
                    raw_value = tag_value.value
                else:
                    raw_value = tag_value
            else:
                # Use get_item for more reliable access
                elem = ds.get_item(tag)
                if elem is None:
                    return None
                raw_value = elem.value
                if raw_value is None:
                    return None
            
            # Check type BEFORE any processing
            # Handle sequences/lists/tuples (multi-value)
            if isinstance(raw_value, (list, tuple)):
                try:
                    # Try to handle pydicom MultiValue
                    from pydicom.multival import MultiValue
                    if isinstance(raw_value, MultiValue):
                        return [str(v).strip() for v in raw_value if v is not None]
                except ImportError:
                    pass
                # Regular list/tuple
                return [str(v).strip() for v in raw_value if v is not None]
            
            # Handle bytes (may contain backslash-separated values)
            if isinstance(raw_value, (bytes, bytearray)):
                try:
                    decoded = raw_value.decode('utf-8', errors='replace')
                    # Check if it contains backslashes (multi-value indicator)
                    if '\\' in decoded:
                        return [v.strip() for v in decoded.split('\\') if v.strip()]
                    else:
                        return decoded.strip()
                except Exception as ex:
                    _logger.debug('Could not decode bytes for tag %s: %s', tag_name, ex)
                    return None
            
            # Handle strings (may contain backslash-separated values or list repr)
            if isinstance(raw_value, str):
                # Check if it's a string representation of a Python list (starts with '[' and ends with ']')
                stripped = raw_value.strip()
                if stripped.startswith('[') and stripped.endswith(']'):
                    try:
                        # Try to parse as a Python list using ast.literal_eval
                        import ast
                        parsed = ast.literal_eval(stripped)
                        if isinstance(parsed, (list, tuple)):
                            return [str(v).strip() for v in parsed if v is not None]
                    except (ValueError, SyntaxError):
                        # If parsing fails, treat as regular string
                        pass
                
                # Check if it contains backslashes (multi-value indicator)
                if '\\' in raw_value:
                    return [v.strip() for v in raw_value.split('\\') if v.strip()]
                else:
                    return raw_value.strip()
            
            # Fallback: convert to string (single value)
            return str(raw_value).strip()
            
        except (AttributeError, ValueError, TypeError, KeyError) as ex:
            _logger.debug('Could not determine value for tag %s: %s', tag_name, ex)
            return None

    _special_image_types = set[str](['localizer', 'scout', 'survey', 'surview', 'top', 'topogram', 'scanogram'])

    def _determine_profile_name(self, ds: pydicom.Dataset):
        from ._profiles import ProfileName
        sop_class_uid = self._safely_extract_value_for_tag(ds, 'SOPClassUID') or ''
        image_type = set[str]([i.lower() for i in self._safely_extract_value_for_tag(ds, 'ImageType') or []])

        if sop_class_uid.startswith('1.2.840.10008.5.1.4.1.1.2'):
            if self._special_image_types.intersection(image_type):
                return ProfileName.CT_LOC
            else:
                return ProfileName.CT_STD
        elif sop_class_uid.startswith('1.2.840.10008.5.1.4.1.1.4'):
            if self._special_image_types.intersection(image_type):
                return ProfileName.MR_LOC
            else:
                return ProfileName.MR_STD
        elif sop_class_uid.startswith('1.2.840.10008.5.1.4.1.1.128'):
            return ProfileName.PET_STD
        elif sop_class_uid.startswith('1.2.840.10008.5.1.4.1.1.7'):
            return ProfileName.SC
        elif sop_class_uid.startswith('1.2.840.10008.5.1.4.1.1.66.4'):
            return ProfileName.SEG

        return ProfileName.GENERIC

    @property
    def profile_name(self) -> str | None:
        from ._profiles import ProfileName
        if self._profile_name is None:
            try:
                ds = self.dcmread(stop_before_pixels=True, force=False)
                self._profile_name = self._determine_profile_name(ds)
                del ds
            except Exception as ex:
                _logger.error(
                    '💥 Unexpected exception reading %s to determine its profile, falling back to generic: %s',
                    self.path, ex
                )
                self._profile_name = ProfileName.GENERIC
        return self._profile_name

    def __repr__(self) -> str:
        '''Return a convenient representation of the potential file.'''
        return (
            f'{self.__class__.__name__}(path={self.path}, site_id={self.site_id}, event_id={self.event_id}, '
            f'file_name={self.file_name})'
        )

    def __str__(self) -> str:
        '''Return a string representation of the potential file.'''
        return self.path

    def __hash__(self) -> int:
        '''Return a hash of the potential file.'''
        return hash(self.path)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PotentialFile):
            return False
        '''Return True if the two potential files are equal.'''
        return self.path == other.path

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PotentialFile):
            return False
        '''Return True if the current potential file is less than the other potential file.'''
        return self.path < other.path