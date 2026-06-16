# encoding: utf-8

'''🛂 EDRN DICOM Validation: PET validators.'''

from ._base import RegexValidator, CaseInsensitiveAndWarningRegexValidator
from .._classes import Validator
from .._files import PotentialFile
from .._findings import ValidationFinding
from .._functions import textify_dicom_value, modality
from pydicom.dataelem import convert_raw_data_element
from pydicom.sequence import Sequence as DICOMSequence
import pydicom, re


_positive_decimal = re.compile(r'^([1-9]\d*(\.\d+)?|0\.\d+)$')
_tm_regex = re.compile(r'^([01][0-9]|2[0-3])[0-5][0-9][0-5][0-9](\.\d+)?$')
_dt_regex = re.compile(r'^[0-9]{14}(\.\d+)?$')

_radiopharmaceutical_start_time_tag = pydicom.tag.Tag((0x0018, 0x1072))
_radiopharmaceutical_start_datetime_tag = pydicom.tag.Tag((0x0018, 0x1078))
_code_value_tag = pydicom.tag.Tag((0x0008, 0x0100))
_coding_scheme_designator_tag = pydicom.tag.Tag((0x0008, 0x0102))


class PatientWeightValidator(RegexValidator):
    '''A validator that checks the PatientWeight tag.'''

    description = "Patient's Weight must be a positive numeric value in kilograms (decimal string; > 0; no units in field)"
    tag = pydicom.tag.Tag((0x0010, 0x1030))
    regex = _positive_decimal


class RadiopharmaceuticalInformationSequenceValidator(Validator):
    '''A validator that checks the RadiopharmaceuticalInformationSequence tag.'''

    description = 'If Modality = PET, RadiopharmaceuticalInformationSequence should contain at least one Item describing the administered radiopharmaceutical'
    tag = pydicom.tag.Tag((0x0054, 0x0016))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        if modality(ds) != 'PET': return findings

        elem = ds.get_item(self.tag)
        if elem is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='RadiopharmaceuticalInformationSequence must contain at least one Item when Modality is PET',
            ))
            return findings

        elem = convert_raw_data_element(elem)
        value = elem.value
        if not isinstance(value, DICOMSequence) or len(value) < 1:
            findings.add(ValidationFinding(
                file=potential_file, value=value, tag=self.tag,
                description='RadiopharmaceuticalInformationSequence must contain at least one Item when Modality is PET',
            ))
        return findings


class RadionuclideCodeSequenceValidator(Validator):
    '''A validator that checks the RadionuclideCodeSequence tag.'''

    description = 'RadionuclideCodeSequence must identify a valid PET radionuclide using standard radionuclide code values (sequence with a single Code Sequence Item)'
    tag = pydicom.tag.Tag((0x0054, 0x0300))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        elem = ds.get_item(self.tag)
        if elem is None:
            return findings

        elem = convert_raw_data_element(elem)
        value = elem.value
        if not isinstance(value, DICOMSequence):
            findings.add(ValidationFinding(
                file=potential_file, value=value, tag=self.tag,
                description='RadionuclideCodeSequence must be a sequence with a single Code Sequence Item',
            ))
            return findings

        if len(value) != 1:
            findings.add(ValidationFinding(
                file=potential_file, value=len(value), tag=self.tag,
                description=f'RadionuclideCodeSequence must contain exactly one Item (got {len(value)})',
            ))
            return findings

        item = value[0]
        code_value = item.get(_code_value_tag)
        coding_scheme = item.get(_coding_scheme_designator_tag)
        if code_value is None or not str(code_value.value).strip():
            findings.add(ValidationFinding(
                file=potential_file, value='CodeValue missing', tag=self.tag,
                description='RadionuclideCodeSequence Item must include a CodeValue identifying the PET radionuclide',
            ))
        elif coding_scheme is None or not str(coding_scheme.value).strip():
            findings.add(ValidationFinding(
                file=potential_file, value='CodingSchemeDesignator missing', tag=self.tag,
                description='RadionuclideCodeSequence Item must follow the DICOM Code Sequence Macro (CodingSchemeDesignator required)',
            ))
        return findings


class RadionuclideTotalDoseValidator(RegexValidator):
    '''A validator that checks the RadionuclideTotalDose tag.'''

    description = 'RadionuclideTotalDose must be a positive numeric value for total injected dose in MBq (decimal string; > 0; no units, spaces, or commas in field)'
    tag = pydicom.tag.Tag((0x0018, 0x1074))
    regex = _positive_decimal


class RadionuclideHalfLifeValidator(RegexValidator):
    '''A validator that checks the RadionuclideHalfLife tag.'''

    description = 'RadionuclideHalfLife must be a positive numeric value in seconds (decimal string; > 0)'
    tag = pydicom.tag.Tag((0x0018, 0x1075))
    regex = _positive_decimal


class RadiopharmaceuticalStartTimeDateTimeValidator(Validator):
    '''A validator that checks RadiopharmaceuticalStartTime and RadiopharmaceuticalStartDateTime tags.'''

    description = 'RadiopharmaceuticalStartTime must be a valid time (HHMMSS[.ffffff]) or RadiopharmaceuticalStartDateTime must be a valid combined date/time (YYYYMMDDHHMMSS[.ffffff])'
    tag = _radiopharmaceutical_start_time_tag

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)

        time_elem = ds.get_item(_radiopharmaceutical_start_time_tag)
        datetime_elem = ds.get_item(_radiopharmaceutical_start_datetime_tag)
        if time_elem is None and datetime_elem is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='RadiopharmaceuticalStartTime or RadiopharmaceuticalStartDateTime must be present',
            ))
            return findings

        if datetime_elem is not None:
            datetime_elem = convert_raw_data_element(datetime_elem)
            for v in textify_dicom_value(datetime_elem.value):
                v = v.strip()
                if not v:
                    continue
                if not _dt_regex.match(v):
                    findings.add(ValidationFinding(
                        file=potential_file, value=v, tag=_radiopharmaceutical_start_datetime_tag,
                        description='RadiopharmaceuticalStartDateTime must be a valid combined date/time in YYYYMMDDHHMMSS[.ffffff] format',
                    ))

        if time_elem is not None:
            time_elem = convert_raw_data_element(time_elem)
            for v in textify_dicom_value(time_elem.value):
                v = v.strip()
                if not v:
                    continue
                if not _tm_regex.match(v):
                    findings.add(ValidationFinding(
                        file=potential_file, value=v, tag=_radiopharmaceutical_start_time_tag,
                        description='RadiopharmaceuticalStartTime must be a valid time in HHMMSS[.ffffff] format',
                    ))

        return findings


class DecayCorrectionValidator(CaseInsensitiveAndWarningRegexValidator):
    '''A validator that checks the DecayCorrection tag.'''

    description = 'DecayCorrection must be a valid PET decay correction value (NONE, START, or ADMIN); uppercase string; length ≤ 16; no leading/trailing spaces'
    tag = pydicom.tag.Tag((0x0054, 0x1102))
    regex = re.compile(r'^(NONE|START|ADMIN)$')
