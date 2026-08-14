# encoding: utf-8

'''🛂 EDRN DICOM Validation: files.'''

from dataclasses import dataclass
from functools import lru_cache
import pydicom, re, os.path, logging
from pydicom import datadict
from pydicom.tag import Tag, BaseTag
from .const import NON_IMAGE_SOP_CLASS_UIDS

_logger = logging.getLogger(__name__)


@dataclass
class PotentialFile:
    '''A file that we will scan for PHI/PII and check for compliance with EDRN validation requirements.'''
    path: str           # Relative path of the file
    site_id: str        # Blinded site ID
    event_id: str       # Event ID
    file_name: str      # File name
    file_size: int      # File size in bytes

    # Regex for parsing organization parts from file paths
    _organization_re = re.compile(r'([^/]+)/(\d{7})/(.+)$')  # blah/blah/Images_site_XYX/1234567/f1/f2/…/file.dcm

    def __init__(self, path: str, site_id: str = None, event_id: str = None, event_id_tag: BaseTag | None = None):
        '''Initialize the potential file with the given file path and optional site and event IDs.

        If `event_id_tag` is given, the Event ID column will instead be populated (once the DICOM
        header is read) with the value of that DICOM tag, taking precedence over both the path-derived
        and any explicitly given `event_id`.
        '''
        self.path = path
        self.file_size = os.path.getsize(path)

        search_result = self._organization_re.search(path)
        if search_result:
            self.site_id, self.event_id, self.file_name = search_result.groups()
        else:
            self.site_id, self.event_id, self.file_name = '«unknown site»', '«unknown event»', os.path.basename(path)

        if site_id: self.site_id = site_id
        if event_id: self.event_id = event_id
        self._event_id_tag = event_id_tag

        # Cached DICOM header metadata (populated on first header read during scan)
        self.sop_class_uid: str = ''
        self.study_instance_uid: str = ''
        self.series_instance_uid: str = ''
        self.report_profile_name: str = ''
        self._header_loaded: bool = False
        self._dicom_readable: bool | None = None

        # Produce on demand; keyed by for_new_data (standard vs new-data profile names differ)
        self._profile_names: dict[bool, object] = {}

    @staticmethod
    def _scalar_tag_value(ds: pydicom.Dataset, tag_name: str, extract) -> str:
        '''Return a single string value for a DICOM tag, or empty string.'''
        value = extract(ds, tag_name) or ''
        if isinstance(value, list):
            value = value[0] if value else ''
        return str(value).strip('\x00').strip()

    def _load_header_metadata(self, for_new_data: bool = False) -> None:
        '''Read DICOM header once and cache profile name and UIDs for scan and reporting.'''
        if self._header_loaded and for_new_data in self._profile_names:
            return
        from ._profiles import ProfileName
        try:
            ds = self.dcmread(stop_before_pixels=True, force=False)
            if not self._header_loaded:
                self.sop_class_uid = self._scalar_tag_value(ds, 'SOPClassUID', self._safely_extract_value_for_tag)
                self.study_instance_uid = self._scalar_tag_value(ds, 'StudyInstanceUID', self._safely_extract_value_for_tag)
                self.series_instance_uid = self._scalar_tag_value(ds, 'SeriesInstanceUID', self._safely_extract_value_for_tag)
                if self._event_id_tag is not None:
                    replacement = self._scalar_tag_value(ds, self._event_id_tag, self._safely_extract_value_for_tag)
                    self.event_id = replacement if replacement else '«unknown event»'
                self._header_loaded = True
                self._dicom_readable = True
            if for_new_data not in self._profile_names:
                self._profile_names[for_new_data] = self._determine_profile_name(ds, for_new_data)
            del ds
        except Exception as ex:
            self._dicom_readable = False
            if for_new_data not in self._profile_names:
                _logger.error(
                    '💥 Unexpected exception reading %s to determine its profile, falling back to generic: %s',
                    self.path, ex
                )
                self._profile_names[for_new_data] = ProfileName.GENERIC

    def _update_report_profile_name(self, for_new_data: bool = False) -> None:
        '''Store the profile name string used for CSV reports.'''
        profile = self._profile_names.get(for_new_data)
        self.report_profile_name = profile.value if profile else 'Unknown'

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

    def _safely_extract_value_for_tag(self, ds: pydicom.Dataset, tag_name: str | BaseTag) -> str | list[str] | None:
        '''Safely extract a value for a DICOM tag.

        `tag_name` may be a keyword (e.g., ``'SOPClassUID'``) or a `pydicom.tag.BaseTag` instance
        (e.g., when a caller has already resolved a ``(group, element)`` tag ID).

        Returns:
            - str: For single-value tags (e.g., SOPClassUID)
            - list[str]: For multi-value tags (e.g., ImageType with backslash-separated values or sequences)
            - None: If the tag doesn't exist or extraction fails
        '''
        try:
            # Convert tag name to tag number for more reliable access
            tag = tag_name if isinstance(tag_name, BaseTag) else datadict.tag_for_keyword(tag_name)
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
    _derived_image_types = set[str](['derived', 'reformatted', 'mpr', 'mip', 'minip', 'average', 'subtracted', 'projection'])

    def _determine_profile_name(self, ds: pydicom.Dataset, for_new_data: bool = False):
        from ._profiles import ProfileName
        sop_class_uid = self._safely_extract_value_for_tag(ds, 'SOPClassUID') or ''
        sop_class_uid = sop_class_uid.rstrip('\x00 \t\r\n')  # Remove trailing null bytes, etc. for #48
        image_types = self._safely_extract_value_for_tag(ds, 'ImageType') or []
        if isinstance(image_types, str): image_types = [image_types]
        image_type = set[str]([i.lower() for i in image_types])

        # Heather wants exact matches on SOPClassUIDs, not prefixes.
        if sop_class_uid == '1.2.840.10008.5.1.4.1.1.2':
            if self._special_image_types.intersection(image_type):
                return ProfileName.CT_LOC_NEW if for_new_data else ProfileName.CT_LOC
            elif self._derived_image_types.intersection(image_type):
                return ProfileName.CT_DER_NEW if for_new_data else ProfileName.CT_DER
            elif len(image_type) == 0:
                return ProfileName.MISSING_IMAGE_TYPE
            else:
                return ProfileName.CT_STD_NEW if for_new_data else ProfileName.CT_STD
        elif sop_class_uid == '1.2.840.10008.5.1.4.1.1.481.3':
            # This must appear before MR_* routing because RTSTRUCT files have an SOPClassUID
            # that starts with 1.2.840.10008.5.1.4.1.1.481.3, which would also be detected as
            # starting with 1.2.840.10008.5.1.4.1.1.4.
            return ProfileName.RTSTRUCT_NEW if for_new_data else ProfileName.RTSTRUCT
        elif sop_class_uid == '1.2.840.10008.5.1.4.1.1.4':
            # Heather's spreadsheet mentions "small matrix helper series" but they're not treated
            # any differently from other MR images so this conditional clause is sufficient.
            # (Not to mention: it's confusing that she cataloged it specially!)
            if self._special_image_types.intersection(image_type):
                return ProfileName.MR_LOC_NEW if for_new_data else ProfileName.MR_LOC
            elif self._derived_image_types.intersection(image_type):
                return ProfileName.MR_DER_NEW if for_new_data else ProfileName.MR_DER
            elif len(image_type) == 0:
                return ProfileName.MISSING_IMAGE_TYPE
            else:
                return ProfileName.MR_STD_NEW if for_new_data else ProfileName.MR_STD
        elif sop_class_uid == '1.2.840.10008.5.1.4.1.1.128':
            return ProfileName.PET_STD_NEW if for_new_data else ProfileName.PET_STD
        elif sop_class_uid == '1.2.840.10008.5.1.4.1.1.1':
            return ProfileName.CR_NEW if for_new_data else ProfileName.CR
        elif sop_class_uid in ['1.2.840.10008.5.1.4.1.1.7', '1.2.840.10008.5.1.4.1.1.7.4']:
            return ProfileName.SC_NEW if for_new_data else ProfileName.SC
        elif sop_class_uid in ['1.2.840.10008.5.1.4.1.1.66.4', '1.2.840.10008.5.1.4.1.1.66']:
            return ProfileName.SEG_NEW if for_new_data else ProfileName.SEG
        elif sop_class_uid in NON_IMAGE_SOP_CLASS_UIDS:
            return ProfileName.NON_IMAGE_DICOM_NEW if for_new_data else ProfileName.NON_IMAGE_DICOM
        elif sop_class_uid == '1.2.840.10008.5.1.4.1.1.1.1':
            return ProfileName.OTHER_IMAGE_NEW if for_new_data else ProfileName.OTHER_IMAGE

        return ProfileName.GENERIC

    def profile_name(self, for_new_data: bool = False):
        self._load_header_metadata(for_new_data)
        return self._profile_names[for_new_data]

    def is_readable_dicom(self) -> bool:
        '''Return True when the file can be parsed as DICOM metadata.'''
        if self._dicom_readable is not None:
            return self._dicom_readable
        try:
            self.dcmread(stop_before_pixels=True, force=False)
            self._dicom_readable = True
            return True
        except Exception:
            self._dicom_readable = False
            return False

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
    
    @property
    def rows(self) -> int:
        '''Return the number of rows in the DICOM file, or 0 if not available.'''
        try:
            # Utterly bizarre behavior! If I call _safely_extract_value_for_tag(…, 'Rows'), I get
            # gibberish binary data. But if I just call it a *second time*, then I get an integer.
            # So forget _safely_extract_value_for_tag, and just ask for Rows directly.
            return int(self.dcmread(stop_before_pixels=True).Rows)
        except Exception as ex:
            _logger.error('🖼️ Could not determine rows for %s: %s', self.path, ex)
            return 0

    @property
    def columns(self) -> int:
        '''Return the number of columns in the DICOM file, or 0 if not available.'''
        try:
            # Utterly bizarre behavior! If I call _safely_extract_value_for_tag(…, 'Columns'), I get
            # gibberish binary data. But if I just call it a *second time*, then I get an integer.
            # So forget _safely_extract_value_for_tag, and just ask for Columns directly.
            return int(self.dcmread(stop_before_pixels=True).Columns)
        except Exception as ex:
            _logger.error('🖼️ Could not determine columns for %s: %s', self.path, ex)
            return 0
