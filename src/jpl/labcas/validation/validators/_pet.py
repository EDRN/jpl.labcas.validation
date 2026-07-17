# encoding: utf-8

'''🛂 EDRN DICOM Validation: PET validators.'''

from ._base import RegexValidator, CaseInsensitiveAndWarningRegexValidator
from .._classes import Validator
from .._files import PotentialFile
from .._findings import ValidationFinding
from .._functions import textify_dicom_value
from pydicom.dataelem import DataElement, convert_raw_data_element
from pydicom.sequence import Sequence as DICOMSequence
import pydicom, re


_positive_decimal = re.compile(r'^([1-9]\d*(\.\d+)?|0\.\d+)$')
_tm_regex = re.compile(r'^([01][0-9]|2[0-3])[0-5][0-9][0-5][0-9](\.\d+)?$')
_dt_regex = re.compile(r'^[0-9]{14}(\.\d+)?$')

_radiopharmaceutical_info_sequence_tag = pydicom.tag.Tag((0x0054, 0x0016))
_radionuclide_code_sequence_tag = pydicom.tag.Tag((0x0054, 0x0300))
_radionuclide_total_dose_tag = pydicom.tag.Tag((0x0018, 0x1074))
_radionuclide_half_life_tag = pydicom.tag.Tag((0x0018, 0x1075))
_radiopharmaceutical_start_time_tag = pydicom.tag.Tag((0x0018, 0x1072))
_radiopharmaceutical_start_datetime_tag = pydicom.tag.Tag((0x0018, 0x1078))
_code_value_tag = pydicom.tag.Tag((0x0008, 0x0100))
_coding_scheme_designator_tag = pydicom.tag.Tag((0x0008, 0x0102))


def _get_sequence(ds: pydicom.Dataset, tag: pydicom.tag.Tag) -> DICOMSequence | None:
    '''Return a converted sequence value from the dataset, or None if absent.'''
    elem = ds.get_item(tag)
    if elem is None:
        return None
    if not isinstance(elem, DataElement):
        elem = convert_raw_data_element(elem)
    value = elem.value
    return value if isinstance(value, DICOMSequence) else None


def _non_empty_text(value) -> str | None:
    '''Return the first non-empty textified value, or None.'''
    if value is None:
        return None
    for v in textify_dicom_value(value):
        v = v.strip()
        if v:
            return v
    return None


def _item_value(item: pydicom.Dataset, tag: pydicom.tag.Tag):
    '''Return a raw element value from a sequence item, or None if absent.'''
    elem = item.get(tag)
    if elem is None:
        return None
    return elem.value


class PatientWeightValidator(RegexValidator):
    '''A validator that checks the PatientWeight tag.'''

    description = "Patient's Weight must be a positive numeric value in kilograms (decimal string; > 0; no units in field)"
    tag = pydicom.tag.Tag((0x0010, 0x1030))
    regex = _positive_decimal


class RadiopharmaceuticalInformationSequenceValidator(Validator):
    '''A validator that checks RadiopharmaceuticalInformationSequence and nested PET injection tags.

    Per the PET Extension spreadsheet, nested tags validated within each sequence Item:
    RadionuclideCodeSequence, RadionuclideTotalDose, RadionuclideHalfLife, and
    RadiopharmaceuticalStartTime or RadiopharmaceuticalStartDateTime.
    '''

    description = (
        'RadiopharmaceuticalInformationSequence must be present with at least one Item; '
        'each Item must include RadionuclideCodeSequence, RadionuclideTotalDose, RadionuclideHalfLife, '
        'and RadiopharmaceuticalStartTime or RadiopharmaceuticalStartDateTime'
    )
    tag = _radiopharmaceutical_info_sequence_tag

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        sequence = _get_sequence(ds, self.tag)
        if sequence is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description=(
                    'RadiopharmaceuticalInformationSequence must be present with at least one Item '
                    'describing the administered radiopharmaceutical'
                ),
            ))
            return findings
        if len(sequence) < 1:
            findings.add(ValidationFinding(
                file=potential_file, value=len(sequence), tag=self.tag,
                description=(
                    'RadiopharmaceuticalInformationSequence must contain at least one Item '
                    'describing the administered radiopharmaceutical'
                ),
            ))
            return findings

        for item in sequence:
            self._validate_radionuclide_code_sequence(findings, potential_file, item)
            self._validate_positive_decimal(
                findings, potential_file, item, _radionuclide_total_dose_tag,
                'RadionuclideTotalDose must be present within RadiopharmaceuticalInformationSequence '
                'as a positive numeric value for total injected dose (decimal string; > 0; no units, spaces, or commas)',
            )
            self._validate_positive_decimal(
                findings, potential_file, item, _radionuclide_half_life_tag,
                'RadionuclideHalfLife must be present within RadiopharmaceuticalInformationSequence '
                'as a positive numeric value in seconds (decimal string; > 0)',
            )
            self._validate_start_time_or_datetime(findings, potential_file, item)

        return findings

    def _validate_radionuclide_code_sequence(
        self, findings: set[ValidationFinding], potential_file: PotentialFile, item: pydicom.Dataset
    ):
        '''Validate nested RadionuclideCodeSequence inside one radiopharmaceutical Item.'''
        code_sequence = getattr(item, 'RadionuclideCodeSequence', None)
        if not isinstance(code_sequence, DICOMSequence):
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=_radionuclide_code_sequence_tag,
                description=(
                    'RadionuclideCodeSequence must be present within RadiopharmaceuticalInformationSequence '
                    'as a sequence with a single Code Sequence Item'
                ),
            ))
            return
        if len(code_sequence) != 1:
            findings.add(ValidationFinding(
                file=potential_file, value=len(code_sequence), tag=_radionuclide_code_sequence_tag,
                description=(
                    f'RadionuclideCodeSequence within RadiopharmaceuticalInformationSequence '
                    f'must contain exactly one Item (got {len(code_sequence)})'
                ),
            ))
            return

        code_item = code_sequence[0]
        code_value = _non_empty_text(_item_value(code_item, _code_value_tag))
        coding_scheme = _non_empty_text(_item_value(code_item, _coding_scheme_designator_tag))
        if code_value is None:
            findings.add(ValidationFinding(
                file=potential_file, value='CodeValue missing', tag=_radionuclide_code_sequence_tag,
                description=(
                    'RadionuclideCodeSequence Item must include a CodeValue identifying the PET radionuclide'
                ),
            ))
        elif coding_scheme is None:
            findings.add(ValidationFinding(
                file=potential_file, value='CodingSchemeDesignator missing', tag=_radionuclide_code_sequence_tag,
                description=(
                    'RadionuclideCodeSequence Item must follow the DICOM Code Sequence Macro '
                    '(CodingSchemeDesignator required)'
                ),
            ))

    def _validate_positive_decimal(
        self,
        findings: set[ValidationFinding],
        potential_file: PotentialFile,
        item: pydicom.Dataset,
        tag: pydicom.tag.Tag,
        description: str,
    ):
        '''Validate a required positive decimal nested tag.'''
        text = _non_empty_text(_item_value(item, tag))
        if text is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=tag, description=description,
            ))
        elif not _positive_decimal.match(text):
            findings.add(ValidationFinding(
                file=potential_file, value=text, tag=tag, description=description,
            ))

    def _validate_start_time_or_datetime(
        self, findings: set[ValidationFinding], potential_file: PotentialFile, item: pydicom.Dataset
    ):
        '''Validate nested RadiopharmaceuticalStartTime or RadiopharmaceuticalStartDateTime.'''
        time_text = _non_empty_text(_item_value(item, _radiopharmaceutical_start_time_tag))
        datetime_text = _non_empty_text(_item_value(item, _radiopharmaceutical_start_datetime_tag))
        if time_text is None and datetime_text is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=_radiopharmaceutical_start_time_tag,
                description=(
                    'RadiopharmaceuticalStartTime or RadiopharmaceuticalStartDateTime must be present '
                    'within RadiopharmaceuticalInformationSequence'
                ),
            ))
            return

        if datetime_text is not None and not _dt_regex.match(datetime_text):
            findings.add(ValidationFinding(
                file=potential_file, value=datetime_text, tag=_radiopharmaceutical_start_datetime_tag,
                description=(
                    'RadiopharmaceuticalStartDateTime within RadiopharmaceuticalInformationSequence '
                    'must be a valid combined date/time in YYYYMMDDHHMMSS[.ffffff] format'
                ),
            ))
        if time_text is not None and not _tm_regex.match(time_text):
            findings.add(ValidationFinding(
                file=potential_file, value=time_text, tag=_radiopharmaceutical_start_time_tag,
                description=(
                    'RadiopharmaceuticalStartTime within RadiopharmaceuticalInformationSequence '
                    'must be a valid time in HHMMSS[.ffffff] format'
                ),
            ))


class DecayCorrectionValidator(CaseInsensitiveAndWarningRegexValidator):
    '''A validator that checks the DecayCorrection tag.'''

    description = 'DecayCorrection must be a valid PET decay correction value (NONE, START, or ADMIN); uppercase string; length ≤ 16; no leading/trailing spaces'
    tag = pydicom.tag.Tag((0x0054, 0x1102))
    regex = re.compile(r'^(NONE|START|ADMIN)$')
