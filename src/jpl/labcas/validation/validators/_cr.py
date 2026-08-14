# encoding: utf-8

'''🛂 EDRN DICOM Validation: CR validators.

The validators in this module are derived from the "CR Extension" tab of the specification spreadsheet.
'''

from ._base import RegexValidator
from .._classes import Validator
from .._files import PotentialFile
from .._findings import ValidationFinding
from .._functions import textify_dicom_value
from pydicom.dataelem import convert_raw_data_element
from collections.abc import Sequence
import pydicom, re


_body_part_examined_tag = pydicom.tag.Tag((0x0018, 0x0015))
_laterality_tag = pydicom.tag.Tag((0x0020, 0x0060))
_image_laterality_tag = pydicom.tag.Tag((0x0020, 0x0062))
_exposure_time_tag = pydicom.tag.Tag((0x0018, 0x1150))
_xray_tube_current_tag = pydicom.tag.Tag((0x0018, 0x1151))
_exposure_tag = pydicom.tag.Tag((0x0018, 0x1152))
_exposure_in_uAs_tag = pydicom.tag.Tag((0x0018, 0x1153))

_positive_decimal = re.compile(r'^([1-9]\d*(\.\d+)?|0\.\d+)$')
_patient_orientation_value = re.compile(r'^[APRLHF]+$')
_laterality_values = frozenset({'R', 'L', 'B', 'U'})
_image_laterality_values = frozenset({'R', 'L'})

# Body Part Examined (0018,0015) defined terms that map to Paired Structure = Y.
# Derived from DICOM PS3.16 Annex L: Table L-1 (human Body Part Examined → SNOMED
# Code Value) then Table L-5 (Pairedness of Anatomic Concepts). Comparison is
# case-insensitive after trimming whitespace.
_paired_body_parts = frozenset({
    'ACJOINT', 'ADRENAL', 'ANKLE', 'ANTECUBITALV', 'ACA', 'ANTTIBIALA', 'ARTERY',
    'AXILLA', 'AXILLARYA', 'AXILLARYV', 'BRACHIALA', 'BRACHIALV', 'BREAST',
    'BRONCHUS', 'BUTTOCK', 'CALCANEUS', 'CALF', 'CAROTID', 'BULB', 'CEPHALICV',
    'CEREBELLUM', 'CEREBRALA', 'CEREBHEMISPHERE', 'CHEEK', 'CHOROIDPLEXUS',
    'CLAVICLE', 'CCA', 'CFA', 'CFV', 'COMILIACA', 'COMILIACV', 'CORNEA', 'EAR',
    'ELBOW', 'EPIDIDYMIS', 'EAC', 'ECA', 'EXTILIACA', 'EXTILIACV', 'EXTJUGV',
    'EXTREMITY', 'EYE', 'EYELID', 'FACIALA', 'FEMORALA', 'FEMORALV', 'FEMUR',
    'FIBULA', 'FINGER', 'FOOT', 'FOREARM', 'GASTRICV', 'GENICULARA', 'GLUTEAL',
    'GSV', 'HAND', 'HEPATICA', 'HEPATICV', 'HIP', 'HUMERUS', 'ILIACA', 'ILIACV',
    'ILIUM', 'INGUINAL', 'INNOMINATEV', 'IAC', 'ICA', 'INTILIACA', 'INTJUGULARV',
    'INTMAMMARYA', 'JOINT', 'KNEE', 'LACRIMALA', 'LATVENTRICLE', 'LINGUALA',
    'LEG', 'LOWERLIMB', 'LUMBARA', 'LUMBAR', 'LUNG', 'MASTOID', 'MAXILLA', 'MCA',
    'OCCPITALA', 'OCCPITALV', 'OPHTHALMICA', 'OPTICCANAL', 'ORBIT', 'OVARY',
    'PARATHYROID', 'PAROTID', 'PATELLA', 'PENILEA', 'PERONEALA', 'POPLITEALA',
    'POPLITEALFOSSA', 'POPLITEALV', 'PCA', 'POSCOMMA', 'POSTIBIALA', 'PROFFEMA',
    'PROFFEMV', 'PULMONARYA', 'PULMONARYV', 'RADIALA', 'RADIUS', 'RADIUSULNA',
    'RENALA', 'RENALV', 'RIB', 'SIJOINT', 'SFJ', 'SAPHENOUSV', 'SCAPULA',
    'SCLERA', 'SCROTUM', 'SESAMOID', 'SHOULDER', 'SCJOINT', 'SUBCLAVIANA',
    'SUBCLAVIANV', 'SUBCOSTAL', 'SUBMANDIBULAR', 'SFA', 'SFV', 'SUPTHYROIDA',
    'SUPRACLAVICULAR', 'TMJ', 'TESTIS', 'THALAMUS', 'THIGH', 'THUMB', 'TIBIA',
    'TIBIAFIBULA', 'TOE', 'ULNA', 'ULNARA', 'UPPERARM', 'UPPERLIMB', 'URETER',
    'VEIN', 'VERTEBRALA', 'WRIST', 'ZYGOMA',
})


def _converted_element(ds: pydicom.Dataset, tag: pydicom.tag.Tag):
    '''Return a converted data element, or None if the tag is absent.'''
    elem = ds.get_item(tag)
    if elem is None:
        return None
    try:
        elem = convert_raw_data_element(elem)
    except AttributeError:
        pass
    return elem


def _texts(ds: pydicom.Dataset, tag: pydicom.tag.Tag) -> list[str] | None:
    '''Return stripped text values for a tag, or None if the tag is absent.'''
    elem = _converted_element(ds, tag)
    if elem is None:
        return None
    if elem.value is None:
        return []
    return [v.strip() for v in textify_dicom_value(elem.value)]


def _first_text(ds: pydicom.Dataset, tag: pydicom.tag.Tag) -> str | None:
    '''Return the first non-empty text value for a tag, or None.'''
    texts = _texts(ds, tag)
    if texts is None:
        return None
    for text in texts:
        if text:
            return text
    return ''


def _is_positive_integer(value: str) -> bool:
    '''Return True when value is an integer greater than zero.'''
    try:
        return int(value) > 0
    except (ValueError, TypeError):
        return False


def _is_integer(value: str) -> bool:
    '''Return True when value is an integer (any sign or zero).'''
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def _is_number(value: str) -> bool:
    '''Return True when value is a valid number.'''
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


class BodyPartExaminedValidator(RegexValidator):
    '''A validator that checks the BodyPartExamined tag.'''

    description = 'BodyPartExamined must contain a non-empty anatomical value'
    tag = _body_part_examined_tag
    regex = re.compile(r'.+')


class ViewPositionValidator(RegexValidator):
    '''A validator that checks the ViewPosition tag.'''

    description = 'ViewPosition must contain a non-empty projection or view value'
    tag = pydicom.tag.Tag((0x0018, 0x5101))
    regex = re.compile(r'.+')


class PatientOrientationValidator(Validator):
    '''A validator that checks the PatientOrientation tag.'''

    description = (
        'PatientOrientation must contain two patient-relative direction values; '
        'each value is a combination of A, P, R, L, H, and F'
    )
    tag = pydicom.tag.Tag((0x0020, 0x0020))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate that PatientOrientation has exactly two anatomical direction values.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        elem = _converted_element(ds, self.tag)
        if elem is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='PatientOrientation tag is missing',
            ))
            return findings
        value = elem.value
        if value is None:
            findings.add(ValidationFinding(
                file=potential_file, value='value missing', tag=self.tag,
                description='PatientOrientation tag found but has no value',
            ))
            return findings
        values_iter = [value] if (isinstance(value, str) or not isinstance(value, Sequence)) else list(value)
        if len(values_iter) != 2:
            findings.add(ValidationFinding(
                file=potential_file, value=value, tag=self.tag,
                description=f'PatientOrientation must be exactly two values (got {len(values_iter)})',
            ))
            return findings
        for i, v in enumerate(values_iter):
            text = str(v).strip()
            if not _patient_orientation_value.match(text):
                findings.add(ValidationFinding(
                    file=potential_file, value=value, tag=self.tag,
                    description=(
                        f'PatientOrientation value {i + 1} must be a combination of '
                        f'A, P, R, L, H, and F (got {text!r})'
                    ),
                ))
                return findings
        return findings


class CRLateralityValidator(Validator):
    '''A validator that checks the shared CR Laterality Rule.

    When BodyPartExamined maps to a paired structure, at least one of Laterality
    (0020,0060) with value R, L, B, or U, or Image Laterality (0020,0062) with
    value R or L, must be present and valid. Invalid populated values are always
    reported, even when the other tag satisfies the rule.
    '''

    description = (
        'When BodyPartExamined is a paired structure, Laterality (R, L, B, or U) '
        'or Image Laterality (R or L) must be present'
    )
    tag = _laterality_tag

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate the CR Laterality Rule.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        body_part = _first_text(ds, _body_part_examined_tag)
        laterality = _first_text(ds, _laterality_tag)
        image_laterality = _first_text(ds, _image_laterality_tag)

        laterality_valid = laterality is not None and laterality.upper() in _laterality_values
        image_laterality_valid = (
            image_laterality is not None and image_laterality.upper() in _image_laterality_values
        )

        if laterality:
            if laterality.upper() not in _laterality_values:
                findings.add(ValidationFinding(
                    file=potential_file, value=laterality, tag=_laterality_tag,
                    description='Laterality, when populated, must be R, L, B, or U',
                ))
        if image_laterality:
            if image_laterality.upper() not in _image_laterality_values:
                findings.add(ValidationFinding(
                    file=potential_file, value=image_laterality, tag=_image_laterality_tag,
                    description='Image Laterality, when populated, must be R or L',
                ))

        if body_part and body_part.upper() in _paired_body_parts:
            if not laterality_valid and not image_laterality_valid:
                findings.add(ValidationFinding(
                    file=potential_file, value=body_part, tag=self.tag,
                    description=(
                        f'BodyPartExamined {body_part!r} is a paired structure; Laterality '
                        f'(R, L, B, or U) or Image Laterality (R or L) must be present'
                    ),
                ))
        return findings


class CRExposureValidator(Validator):
    '''A validator that checks the shared CR Exposure Rule.

    The rule is satisfied when (ExposureTime and X-Ray Tube Current are both
    positive integers) or Exposure is a positive integer or Exposure in µAs is
    a positive integer. Populated tags that are not positive integers are always
    reported.
    '''

    description = (
        'CR Exposure Rule: (ExposureTime and X-Ray Tube Current) or Exposure or '
        'Exposure in µAs must be present as a positive integer'
    )
    tag = _exposure_tag

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate the CR Exposure Rule.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)

        exposure_time = _first_text(ds, _exposure_time_tag)
        tube_current = _first_text(ds, _xray_tube_current_tag)
        exposure = _first_text(ds, _exposure_tag)
        exposure_uas = _first_text(ds, _exposure_in_uAs_tag)

        time_valid = bool(exposure_time) and _is_positive_integer(exposure_time)
        current_valid = bool(tube_current) and _is_positive_integer(tube_current)
        exposure_valid = bool(exposure) and _is_positive_integer(exposure)
        uas_valid = bool(exposure_uas) and _is_positive_integer(exposure_uas)

        if exposure_time and not _is_positive_integer(exposure_time):
            findings.add(ValidationFinding(
                file=potential_file, value=exposure_time, tag=_exposure_time_tag,
                description='ExposureTime, when populated, must be an integer greater than zero',
            ))
        if tube_current and not _is_positive_integer(tube_current):
            findings.add(ValidationFinding(
                file=potential_file, value=tube_current, tag=_xray_tube_current_tag,
                description='X-Ray Tube Current, when populated, must be an integer greater than zero',
            ))
        if exposure and not _is_positive_integer(exposure):
            findings.add(ValidationFinding(
                file=potential_file, value=exposure, tag=_exposure_tag,
                description='Exposure, when populated, must be an integer greater than zero',
            ))
        if exposure_uas and not _is_positive_integer(exposure_uas):
            findings.add(ValidationFinding(
                file=potential_file, value=exposure_uas, tag=_exposure_in_uAs_tag,
                description='Exposure in µAs, when populated, must be an integer greater than zero',
            ))

        if not ((time_valid and current_valid) or exposure_valid or uas_valid):
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description=(
                    'CR Exposure Rule: (ExposureTime and X-Ray Tube Current) or Exposure '
                    'or Exposure in µAs must be present as a positive integer'
                ),
            ))
        return findings


class ImagerPixelSpacingValidator(Validator):
    '''A validator that checks ImagerPixelSpacing when the tag is present.'''

    description = 'ImagerPixelSpacing, if present, must contain two numeric values greater than zero'
    tag = pydicom.tag.Tag((0x0018, 0x1164))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate ImagerPixelSpacing when the tag is present.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        elem = _converted_element(ds, self.tag)
        if elem is None:
            return findings
        value = elem.value
        if value is None:
            findings.add(ValidationFinding(
                file=potential_file, value='value missing', tag=self.tag,
                description='ImagerPixelSpacing tag found but has no value',
            ))
            return findings
        values_iter = [value] if (isinstance(value, str) or not isinstance(value, Sequence)) else list(value)
        if len(values_iter) != 2:
            findings.add(ValidationFinding(
                file=potential_file, value=value, tag=self.tag,
                description=f'ImagerPixelSpacing must be exactly two values (got {len(values_iter)})',
            ))
            return findings
        for i, v in enumerate(values_iter):
            try:
                n = float(v)
            except (ValueError, TypeError):
                findings.add(ValidationFinding(
                    file=potential_file, value=value, tag=self.tag,
                    description=f'ImagerPixelSpacing value {i + 1} must be a number greater than zero',
                ))
                return findings
            if n <= 0:
                findings.add(ValidationFinding(
                    file=potential_file, value=value, tag=self.tag,
                    description=f'ImagerPixelSpacing values must be greater than zero (value {i + 1} is {n})',
                ))
                return findings
        return findings


class PatientPositionValidator(RegexValidator):
    '''A validator that checks PatientPosition when the tag is present.'''

    description = 'PatientPosition, if present, must contain a non-empty position value'
    tag = pydicom.tag.Tag((0x0018, 0x5100))
    regex = re.compile(r'.+')

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate PatientPosition only when the tag is present.'''
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        if ds.get_item(self.tag) is None:
            return set()
        return super().validate(potential_file)


class KVPValidator(RegexValidator):
    '''A validator that checks KVP when the tag is present.'''

    description = 'KVP, if present, must be a numeric value greater than zero'
    tag = pydicom.tag.Tag((0x0018, 0x0060))
    regex = _positive_decimal

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate KVP only when the tag is present.'''
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        if ds.get_item(self.tag) is None:
            return set()
        return super().validate(potential_file)


class DistanceSourceToDetectorValidator(RegexValidator):
    '''A validator that checks DistanceSourceToDetector when the tag is present.'''

    description = 'DistanceSourceToDetector, if present, must be a numeric value greater than zero'
    tag = pydicom.tag.Tag((0x0018, 0x1110))
    regex = _positive_decimal

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate DistanceSourceToDetector only when the tag is present.'''
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        if ds.get_item(self.tag) is None:
            return set()
        return super().validate(potential_file)


class DistanceSourceToPatientValidator(RegexValidator):
    '''A validator that checks DistanceSourceToPatient when the tag is present.'''

    description = 'DistanceSourceToPatient, if present, must be a numeric value greater than zero'
    tag = pydicom.tag.Tag((0x0018, 0x1111))
    regex = _positive_decimal

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate DistanceSourceToPatient only when the tag is present.'''
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        if ds.get_item(self.tag) is None:
            return set()
        return super().validate(potential_file)


class RelativeXRayExposureValidator(Validator):
    '''A validator that checks RelativeXRayExposure when the tag is present.'''

    description = 'RelativeXRayExposure, if present, must be a valid integer'
    tag = pydicom.tag.Tag((0x0018, 0x1405))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate RelativeXRayExposure when the tag is present.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        text = _first_text(ds, self.tag)
        if text is None:
            return findings
        if not text or not _is_integer(text):
            findings.add(ValidationFinding(
                file=potential_file, value=text if text else 'value missing', tag=self.tag,
                description='RelativeXRayExposure, if present, must be a valid integer',
            ))
        return findings


class SensitivityValidator(Validator):
    '''A validator that checks Sensitivity when the tag is present.'''

    description = 'Sensitivity, if present, must be a valid numeric value'
    tag = pydicom.tag.Tag((0x0018, 0x6000))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate Sensitivity when the tag is present.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        text = _first_text(ds, self.tag)
        if text is None:
            return findings
        if not text or not _is_number(text):
            findings.add(ValidationFinding(
                file=potential_file, value=text if text else 'value missing', tag=self.tag,
                description='Sensitivity, if present, must be a valid numeric value',
            ))
        return findings
