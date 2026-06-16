# encoding: utf-8

'''🛂 EDRN DICOM Validation: MR validators.'''

from ._base import RegexValidator, DICOMUIDValidator
from .._classes import Validator
from .._files import PotentialFile
from .._findings import ValidationFinding
from .._functions import modality
from pydicom.dataelem import convert_raw_data_element
from collections.abc import Sequence
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

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        if modality(ds) != 'MR': return findings

        # Only validate SpacingBetweenSlices when there are multiple slices in the series
        if self._has_multiple_slices_in_series(ds):
            other_findings = super().validate(potential_file)
            current_series_uid = getattr(ds, 'SeriesInstanceUID', None)

            # @hoodriverheather wants the description to be more precise and not just "missing tag"
            for finding in other_findings:
                if current_series_uid is not None:
                    finding.description = f'Multiple DICOM files in the series (with the same SeriesInstanceUID {current_series_uid}) must have the SpacingBetweenSlices tag—in every file'
                else:
                    finding.description = 'Multiple DICOM files in the series (with the same SeriesInstanceUID) must have the SpacingBetweenSlices tag—in every file'

            findings.update(other_findings)
        return findings


class AcquisitionMatrixValidator(Validator):
    '''A validator that checks the AcquisitionMatrix tag.'''

    description = 'AcquisitionMatrix, if present, must contain four non-negative integers'
    tag = pydicom.tag.Tag((0x0018, 0x1310))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate AcquisitionMatrix when the tag is present.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        elem = ds.get_item(self.tag)
        if elem is None:
            return findings

        elem = convert_raw_data_element(elem)
        value = elem.value
        if value is None:
            findings.add(ValidationFinding(
                file=potential_file, value='value missing', tag=self.tag,
                description='AcquisitionMatrix tag found but has no value',
            ))
            return findings

        values_iter = [value] if (isinstance(value, str) or not isinstance(value, Sequence)) else list(value)
        if len(values_iter) != 4:
            findings.add(ValidationFinding(
                file=potential_file, value=value, tag=self.tag,
                description=f'AcquisitionMatrix must be exactly four values (got {len(values_iter)})',
            ))
            return findings

        for i, v in enumerate(values_iter):
            try:
                n = int(v)
            except (ValueError, TypeError):
                findings.add(ValidationFinding(
                    file=potential_file, value=value, tag=self.tag,
                    description=f'AcquisitionMatrix value {i + 1} must be a non-negative integer',
                ))
                return findings
            if n < 0:
                findings.add(ValidationFinding(
                    file=potential_file, value=value, tag=self.tag,
                    description=f'AcquisitionMatrix value {i + 1} must be non-negative (got {n})',
                ))
                return findings

        return findings


class MisterImageTypeValidator(RegexValidator):
    '''A validator that checks the ImageType tag for MR data only (Mister Data)
    
    Mister Data at one time should just be the word "LOCALIZER", but it can actually
    be anything.
    '''
    description = 'ImageType for MR data can be anything up to 128 characters long'
    tag = pydicom.tag.Tag((0x0008, 0x0008))
    # Old pattern: the word "LOCALIZER"
    # regex = re.compile(r'^LOCALIZER$', re.IGNORECASE)
    # New pattern: any string up to 128 characters long
    regex = re.compile(r'^.{1,128}$')


class DiffusionBValueValidator(RegexValidator):
    '''A validator that checks the DiffusionBValue tag for presence only.'''

    description = 'DiffusionBValue must be present'
    tag = pydicom.tag.Tag((0x0018, 0x9087))
    regex = re.compile(r'.+')

