# encoding: utf-8

'''🛂 EDRN DICOM Validation: MR validators.'''

from ._base import RegexValidator, DICOMUIDValidator
from .._classes import ValidationFinding
from .._functions import modality
import pydicom, re, os, logging

_logger = logging.getLogger(__name__)


class SpacingBetweenSlicesValidator(RegexValidator):
    '''A validator that checks the SpacingBetweenSlices tag.'''

    description = 'SpacingBetweenSlices must be a positive number, floating point or integer, and is optional'
    tag = pydicom.tag.Tag((0x0018, 0x0088))
    regex = re.compile(r'^([1-9]\d*(\.\d+)?|0\.\d+)?$')
    series_instance_uids: set[str] = set()


    def _has_multiple_slices_in_series(self, ds: pydicom.Dataset) -> bool:
        '''Check if there are multiple slices in the same series.
        
        This checks the directory containing the current DICOM file for other
        DICOM files with the same SeriesInstanceUID.
        '''
        _logger.debug('🧐 Checking for multiple slices in series in %s', ds.filename)
        if not hasattr(ds, 'filename') or not ds.filename: return False
        
        # Get the directory and SeriesInstanceUID of the current file
        directory = os.path.dirname(ds.filename)
        if not os.path.isdir(directory): return False
        
        try:
            current_series_uid = getattr(ds, 'SeriesInstanceUID', None)
            if current_series_uid in self.series_instance_uids: return True
            if not current_series_uid: return False
            
            # Check for other DICOM files in the same directory with the same SeriesInstanceUID
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                if not os.path.isfile(filepath): continue
                
                # Skip the current file
                if os.path.samefile(filepath, ds.filename): continue
                
                try:
                    # Try to read as DICOM and check SeriesInstanceUID (stop_before_pixels=True for efficiency)
                    other_ds = pydicom.dcmread(filepath, stop_before_pixels=True, force=False)
                    other_series_uid = getattr(other_ds, 'SeriesInstanceUID', None)
                    if current_series_uid == other_series_uid:
                        # Found at least one other slice in the same series
                        _logger.debug(
                            '✅ Found at least one other slice in the same series %s in %s',
                            current_series_uid, ds.filename
                        )
                        self.series_instance_uids.add(current_series_uid)
                        return True
                except (pydicom.errors.InvalidDicomError, IOError, Exception):
                    # Not a valid DICOM file or can't read it, skip
                    continue
            
            return False
        except Exception:
            # If anything goes wrong, assume false
            return False

    def validate(self, ds: pydicom.Dataset) -> list[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        findings: list[ValidationFinding] = []
        if modality(ds) != 'MR': return findings

        # Only validate SpacingBetweenSlices when there are multiple slices in the series
        if self._has_multiple_slices_in_series(ds):
            other_findings = super().validate(ds)
            current_series_uid = getattr(ds, 'SeriesInstanceUID', None)

            # @hoodriverheather wants the description to be more precise and not just "missing tag"
            for finding in other_findings:
                if current_series_uid is not None:
                    finding.description = f'Multiple DICOM files in the series (with the same SeriesInstanceUID {current_series_uid}) must have the SpacingBetweenSlices tag—in every file'
                else:
                    finding.description = 'Multiple DICOM files in the series (with the same SeriesInstanceUID) must have the SpacingBetweenSlices tag—in every file'

            findings.extend(other_findings)
        return findings


class AcquisitionMatrixValidator(RegexValidator):
    '''A validator that checks the AcquisitionMatrix tag.'''

    description = 'AcquisitionMatrix must be four non-negative integers'
    tag = pydicom.tag.Tag((0x0018, 0x0080))
    regex = re.compile(r'^\[(\d+,\s*){3}\d+\]$')

    def validate(self, ds: pydicom.Dataset) -> list[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        findings: list[ValidationFinding] = []
        if modality(ds) != 'MR': return findings

        # Only bother to validate AcquisitionMatrix if tag (0018, 1310) exists and has a value
        elem = ds.get_item((0x0018, 0x1310))
        if elem is not None and elem.value:
            findings.extend(super().validate(ds))
        return findings
