# encoding: utf-8

'''🛂 EDRN DICOM Validation: core validators.

The validators in this module are derived from the "CORE" tab of @hoodriverheather's spreadsheet at:

https://docs.google.com/spreadsheets/d/1MPSEOMTVnT-eVL8AXLXVebuBOqNDSxrz_cqAV1az_N4/edit?gid=1392488545#gid=1392488545
'''

from .._classes import Validator
from .._files import PotentialFile
from .._findings import ValidationFinding, WarningFinding
from .._functions import textify_dicom_value, is_anonymized_value
from ._base import RegexValidator, DICOMUIDValidator, YMDValidator, CaseInsensitiveAndWarningRegexValidator
from pydicom.dataelem import convert_raw_data_element
from collections.abc import Sequence
import pydicom, re, logging

_logger = logging.getLogger(__name__)


# Study, Series, and Image Identification
# ---------------------------------------

class SeriesDescriptionValidator(RegexValidator):
    '''A validator that checks the SeriesDescription tag.'''

    description = 'SeriesDescription must be present and non-empty'
    tag = pydicom.tag.Tag((0x0008, 0x103E))
    regex = re.compile(r'.+')
    

class StudyInstanceUIDValidator(DICOMUIDValidator):
    '''A validator that checks the StudyInstanceUID tag.'''

    description = 'StudyInstanceUID must be a valid DICOM UID of digits and dots; at least one dot, no leading/trailing dots; up to 64 characters'
    tag = pydicom.tag.Tag((0x0020, 0x000D))


class SeriesInstanceUIDValidator(DICOMUIDValidator):
    '''A validator that checks the SeriesInstanceUID tag.'''

    description = 'SeriesInstanceUID must be a valid DICOM UID of digits and dots; at least one dot, no leading/trailing dots; up to 64 characters'
    tag = pydicom.tag.Tag((0x0020, 0x000E))


class SeriesNumberValidator(RegexValidator):
    '''A validator that checks the SeriesNumber tag.'''

    description = 'SeriesNumber must be a valid DICOM UID of digits and dots; at least one dot, no leading/trailing dots; up to 64 characters'
    tag = pydicom.tag.Tag((0x0020, 0x0011))
    regex = re.compile(r'^(?=.{1,64}$)[0-9]+$')


class InstanceNumberValidator(RegexValidator):
    '''A validator that checks the InstanceNumber tag.'''

    description = 'InstanceNumber must be a positive integer'
    tag = pydicom.tag.Tag((0x0020, 0x0013))
    regex = re.compile(r'^[1-9][0-9]*$')


class SOPClassUIDValidator(DICOMUIDValidator):
    '''A validator that checks the SOPClassUID tag.'''

    description = 'SOPClassUID must be a valid DICOM UID of digits and dots; at least one dot, no leading/trailing dots; up to 64 characters'
    tag = pydicom.tag.Tag((0x0008, 0x0016))


# Acquisition Modality and Equipment
# ----------------------------------

class ModalityValidator(CaseInsensitiveAndWarningRegexValidator):
    '''A validator that checks the Modality tag.'''

    description = 'Modality must be a valid DICOM code (CT, MR, MG, PT, etc.)'
    tag = pydicom.tag.Tag((0x0008, 0x0060))
    # Valid DICOM Modality codes per PS3.3 C.7.3.1.1.1
    regex = re.compile(r'^(ANN|AR|AS|ASMT|AU|BDUS|BI|BMD|CD|CF|CFM|CP|CR|CS|CT|CTPROTOCOL|DD|DF|DG|DM|DMS|DOC|DS|DX|EC|ECG|EEG|EMG|EOG|EPS|ES|FA|FID|FS|GM|HC|HD|IO|IOL|IVOCT|IVUS|KER|KO|LEN|LP|LS|M3D|MA|MG|MR|MS|NM|OAM|OCT|OP|OPM|OPR|OPT|OPTBSV|OPTENF|OPV|OSS|OT|PA|PLAN|POS|PR|PT|PX|REG|RESP|RF|RG|RTDOSE|RTIMAGE|RTINTENT|RTPLAN|RTRECORD|RTRAD|RTSEGANN|RTSTRUCT|RTV|RWV|SC|SEG|SM|SMR|SR|SRF|ST|STAIN|TEXTUREMAP|TG|US|VA|VF|XA|XC|XCD)$')


class ManufacturerValidator(RegexValidator):
    '''A validator that checks the Manufacturer tag.'''

    description = 'Manufacturer cannot have leading or trailing space'
    tag = pydicom.tag.Tag((0x0008, 0x0070))
    regex = re.compile(r'^(?=.{1,64}$)\S+(?:\s+\S+)*$')


class ModelNameValidator(RegexValidator):
    '''A validator that checks the ModelName tag.'''

    description = 'ModelName cannot have leading or trailing space'
    tag = pydicom.tag.Tag((0x0008, 0x1090))
    regex = re.compile(r'^(?=.{1,64}$)\S+(?:\s+\S+)*$')


class SoftwareVersionsValidator(RegexValidator):
    '''A validator that checks the SoftwareVersions tag.'''

    description = 'SoftwareVersions cannot have leading or trailing space'
    tag = pydicom.tag.Tag((0x0018, 0x1020))
    regex = re.compile(r'^(?=.{1,64}$)\S+(?:\s+\S+)*$')


# Temporal and Acquisition Timing
# ------------------------------

class StudyDateValidator(YMDValidator):
    '''A validator that checks the StudyDate tag.'''

    description = 'StudyDate must be a valid date in YYYYMMDD format'
    tag = pydicom.tag.Tag((0x0008, 0x0020))


class ContentDateValidator(YMDValidator):
    '''A validator that checks the ContentDate tag.'''

    description = 'ContentDate must be a valid date in YYYYMMDD format'
    tag = pydicom.tag.Tag((0x0008, 0x0023))


class AcquisitionDateValidator(YMDValidator):
    '''A validator that checks the AcquisitionDate tag.'''

    description = 'AcquisitionDate must be a valid date in YYYYMMDD format'
    tag = pydicom.tag.Tag((0x0008, 0x0022))


class AcquisitionTimeValidator(RegexValidator):
    '''A validator that checks the AcquisitionTime tag.'''

    description = 'AcquisitionTime must be a valid time in HHMMSS[.ffffff] format'
    tag = pydicom.tag.Tag((0x0008, 0x0032))
    regex = re.compile(r'^([01][0-9]|2[0-3])[0-5][0-9][0-5][0-9](\.\d+)?$')


class ContentTimeValidator(RegexValidator):
    '''A validator that checks the ContentTime tag.'''

    description = 'ContentTime "Image Time" must be a valid time in HHMMSS[.ffffff] format'
    tag = pydicom.tag.Tag((0x0008, 0x0033))
    regex = re.compile(r'^([01][0-9]|2[0-3])[0-5][0-9][0-5][0-9](\.\d+)?$')


# Image Data, Dimensions, and Display Parameters
# ----------------------------------------------

class RowsValidator(RegexValidator):
    '''A validator that checks the Rows tag.'''

    description = 'Rows must be a positive integer and ≤ 5 digits'
    tag = pydicom.tag.Tag((0x0028, 0x0010))
    regex = re.compile(r'^[1-9]\d{0,4}$')


class ColumnsValidator(RegexValidator):
    '''A validator that checks the Columns tag.'''

    description = 'Columns must be a positive integer and ≤ 5 digits'
    tag = pydicom.tag.Tag((0x0028, 0x0011))
    regex = re.compile(r'^[1-9]\d{0,4}$')


class SOPInstanceUIDValidator(DICOMUIDValidator):
    '''A validator that checks the SOPInstanceUID tag.'''

    description = 'SOPInstanceUID must be a valid DICOM UID of digits and dots; at least one dot, no leading/trailing dots; up to 64 characters'
    tag = pydicom.tag.Tag((0x0008, 0x0018))


class BitsAllocatedValidator(RegexValidator):
    '''A validator that checks the BitsAllocated tag.'''

    description = 'BitsAllocated must be a positive integer and ≤ 2 digits'
    tag = pydicom.tag.Tag((0x0028, 0x0100))
    regex = re.compile(r'^[1-9]\d{0,1}$')


class BitsStoredValidator(RegexValidator):
    '''A validator that checks the BitsStored tag.'''

    description = 'BitsStored must be a positive integer and ≤ 2 digits'
    tag = pydicom.tag.Tag((0x0028, 0x0101))
    regex = re.compile(r'^[1-9]\d{0,1}$')


class HighBitValidator(RegexValidator):
    '''A validator that checks the HighBit tag.'''

    description = 'HighBit must be a positive integer and ≤ 2 digits'
    tag = pydicom.tag.Tag((0x0028, 0x0102))
    regex = re.compile(r'^[1-9]\d{0,1}$')


class PixelRepresentationValidator(RegexValidator):
    '''A validator that checks the PixelRepresentation tag.'''

    description = 'PixelRepresentation must be 0 or 1'
    tag = pydicom.tag.Tag((0x0028, 0x0103))
    regex = re.compile(r'^(0|1)$')


class PhotometricInterpretationValidator(CaseInsensitiveAndWarningRegexValidator):
    '''A validator that checks the PhotometricInterpretation tag.'''

    description = 'PhotometricInterpretation must be a valid DICOM code (MONOCHROME1, MONOCHROME2, PALETTE_COLOR, RGB, YBR_FULL, YBR_PARTIAL_422, etc.)'
    tag = pydicom.tag.Tag((0x0028, 0x0004))
    # 🔮 Might be nicer to have a "controlled vocabulary" base class so that validators like this
    # one can just simply list their allowed values rather than come up with a regex.
    regex = re.compile(r'^(MONOCHROME1|MONOCHROME2|PALETTE_COLOR|RGB|YBR_FULL)$')


class WindowCenterValidator(Validator):
    '''A validator that checks the WindowCenter tag.'''

    description = 'WindowCenter must be an integer or floating point number; multiple numbers separated by backslashes are allowed'
    tag = pydicom.tag.Tag((0x0028, 0x1050))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        findings: set[ValidationFinding] = set()

        # Validate the WindowCenter tag only if the PhotometricInterpretation is MONOCHROME1 or MONOCHROME2
        photometric_interpretation = ds.get_item((0x0028, 0x0004))
        if photometric_interpretation is not None:
            value = textify_dicom_value(photometric_interpretation.value)
            if any(v.strip() in ('MONOCHROME1', 'MONOCHROME2') for v in value):
                elem = ds.get_item(self.tag)
                if elem is not None:
                    values = convert_raw_data_element(elem).value
                    # Normalize values to always be iterable (handle both MultiValue and single values like DSfloat)
                    if values is None:
                        values_iter = []
                    elif isinstance(values, str) or not isinstance(values, Sequence):
                        values_iter = [values]
                    else:
                        values_iter = values
                    try:
                        [float(v) for v in values_iter]
                    except (ValueError, TypeError):
                        findings.add(ValidationFinding(
                            file=potential_file, value=values, tag=self.tag,
                            description=f'WindowCenter must be an integer or floating point number'
                        ))
                else:
                    findings.add(ValidationFinding(
                        file=potential_file, value='value missing', tag=self.tag,
                        description=f'WindowCenter tag is missing but required for MONOCHROME1 or MONOCHROME2 PhotometricInterpretation'
                    ))
        return findings


class WindowWidthValidator(RegexValidator):
    '''A validator that checks the WindowWidth tag.'''

    # 🔮 TODO: refactor this with the WindowCenterValidator class

    description = 'WindowWidth must be an integer or floating point number; multiple numbers separated by backslashes are allowed'
    tag = pydicom.tag.Tag((0x0028, 0x1051))
    regex = re.compile(r'^-?(\d+\.\d*|\d*\.\d+|\d+)(\\-?(\d+\.\d*|\d*\.\d+|\d+))*$')

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        findings: set[ValidationFinding] = set()

        # Validate the WindowCenter tag only if the PhotometricInterpretation is MONOCHROME1 or MONOCHROME2
        photometric_interpretation = ds.get_item((0x0028, 0x0004))
        if photometric_interpretation is not None:
            value = textify_dicom_value(photometric_interpretation.value)
            if any(v.strip() in ('MONOCHROME1', 'MONOCHROME2') for v in value):
                elem = ds.get_item(self.tag)
                if elem is not None:
                    values = convert_raw_data_element(elem).value
                    # Normalize values to always be iterable (handle both MultiValue and single values like DSfloat)
                    if values is None:
                        values_iter = []
                    elif isinstance(values, str) or not isinstance(values, Sequence):
                        values_iter = [values]
                    else:
                        values_iter = values
                    try:
                        [float(v) for v in values_iter]
                    except (ValueError, TypeError):
                        findings.add(ValidationFinding(
                            file=potential_file, value=values, tag=self.tag,
                            description=f'WindowCenter must be an integer or floating point number'
                        ))
                else:
                    findings.add(ValidationFinding(
                        file=potential_file, value='value missing', tag=self.tag,
                        description=f'WindowWidth tag is missing but required for MONOCHROME1 or MONOCHROME2 PhotometricInterpretation'
                    ))
        return findings


class PixelSpacingValidator(Validator):
    '''A validator that checks the PixelSpacing tag.'''

    description = 'PixelSpacing must be a pair of positive floating point numbers'
    tag = pydicom.tag.Tag((0x0028, 0x0030))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate that PixelSpacing has exactly two positive floats (e.g. decimal or scientific notation).'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        elem = ds.get_item(self.tag)
        if elem is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='PixelSpacing tag is missing'
            ))
            return findings
        elem = convert_raw_data_element(elem)
        value = elem.value
        if value is None:
            findings.add(ValidationFinding(
                file=potential_file, value='value missing', tag=self.tag,
                description='PixelSpacing tag has no value'
            ))
            return findings
        values_iter = [value] if (isinstance(value, str) or not isinstance(value, Sequence)) else list(value)
        if len(values_iter) != 2:
            findings.add(ValidationFinding(
                file=potential_file, value=value, tag=self.tag,
                description=f'PixelSpacing must be exactly two values (got {len(values_iter)})'
            ))
            return findings
        for i, v in enumerate(values_iter):
            try:
                n = float(v)
            except (ValueError, TypeError):
                findings.add(ValidationFinding(
                    file=potential_file, value=value, tag=self.tag,
                    description=f'PixelSpacing value {i + 1} must be a floating point number (decimal or scientific notation)'
                ))
                return findings
            if n <= 0:
                findings.add(ValidationFinding(
                    file=potential_file, value=value, tag=self.tag,
                    description=f'PixelSpacing values must be positive (value {i + 1} is {n})'
                ))
                return findings
        return findings


class ImagePositionPatientValidator(Validator):
    '''A validator that checks the ImagePositionPatient tag.'''

    description = 'ImagePositionPatient must be a triplet of floating point numbers'
    tag = pydicom.tag.Tag((0x0020, 0x0032))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate that ImagePositionPatient has exactly three floats (e.g. decimal or scientific notation).'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        elem = ds.get_item(self.tag)
        if elem is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='ImagePositionPatient tag is missing'
            ))
            return findings
        elem = convert_raw_data_element(elem)
        value = elem.value
        if value is None:
            findings.add(ValidationFinding(
                file=potential_file, value='value missing', tag=self.tag,
                description='ImagePositionPatient tag has no value'
            ))
            return findings
        values_iter = [value] if (isinstance(value, str) or not isinstance(value, Sequence)) else list(value)
        if len(values_iter) != 3:
            findings.add(ValidationFinding(
                file=potential_file, value=value, tag=self.tag,
                description=f'ImagePositionPatient must be exactly three values (got {len(values_iter)})'
            ))
            return findings
        for i, v in enumerate(values_iter):
            try:
                float(v)
            except (ValueError, TypeError):
                findings.add(ValidationFinding(
                    file=potential_file, value=value, tag=self.tag,
                    description=f'ImagePositionPatient value {i + 1} must be a floating point number (decimal or scientific notation)'
                ))
                return findings
        return findings


class ImageOrientationPatientValidator(Validator):
    '''A validator that checks the ImageOrientationPatient tag.'''

    description = 'ImageOrientationPatient must be a 6 numeric values'
    tag = pydicom.tag.Tag((0x0020, 0x0037))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        elem = ds.get_item(self.tag)
        if elem is not None:
            elem = convert_raw_data_element(elem)
            if elem.value is None:
                finding = ValidationFinding(
                    file=potential_file, value='ImageOrientationPatient tag value has null values', tag=self.tag,
                    description='ImageOrientationPatient tag value has null values'
                )
                findings.add(finding)
            else:
                count = 0
                for v in elem.value:
                    try:
                        float(v)
                        count += 1
                    except ValueError:
                        break
                if count != 6:
                    finding = ValidationFinding(
                        file=potential_file, value=str(elem.value), tag=self.tag,
                        description='ImageOrientationPatient must be a 6 numeric values'
                    )
                    findings.add(finding)
        else:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='ImageOrientationPatient tag is missing')
            )
        return findings


 # Image Type and Characteristics
 # ------------------------------

class ImageTypeValidator(Validator):
    '''A validator that checks the ImageType tag.'''

    description = 'ImageType must be a 1 or more strings with the first string being "ORIGINAL" or "DERIVED", the second (if present) must be "PRIMARY" or "SECONDARY"; additional strings are allowed'
    tag = pydicom.tag.Tag((0x0008, 0x0008))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        elem = ds.get_item(self.tag)
        if elem is not None:
            if elem.value is None:
                findings.add(ValidationFinding(
                    file=potential_file, value='ImageType tag value has null values', tag=self.tag,
                    description='ImageType tag value has null values'
                ))
            else:
                try:
                    values = elem.value.decode().split('\\')
                    if len(values) > 0:
                        val0 = values[0].strip()
                        # Skip anonymized values (starts with "anon" or matches "Doe John" patterns)
                        if not is_anonymized_value(val0):
                            if val0.upper() not in ('ORIGINAL', 'DERIVED'):
                                if val0 in ('original', 'derived'):
                                    findings.add(WarningFinding(
                                        file=potential_file, value=val0, tag=self.tag,
                                        description=f'ImageType must start with "ORIGINAL" or "DERIVED" in ALL CAPS'
                                    ))
                                else:
                                    findings.add(ValidationFinding(
                                        file=potential_file, value=val0, tag=self.tag,
                                        description=f'ImageType must start with "ORIGINAL" or "DERIVED"'
                                    ))
                        if len(values) > 1:
                            val1 = values[1].strip()
                            # Skip anonymized values (starts with "anon" or matches "Doe John" patterns)
                            if not is_anonymized_value(val1):
                                if val1.upper() not in ('PRIMARY', 'SECONDARY'):
                                    if val1 in ('primary', 'secondary'):
                                        findings.add(WarningFinding(
                                            file=potential_file, value=val1, tag=self.tag,
                                            description=f'ImageType must have a second string that is "PRIMARY" or "SECONDARY" in ALL CAPS'
                                        ))
                                    else:
                                        findings.add(ValidationFinding(
                                            file=potential_file, value=val1, tag=self.tag,
                                            description=f'ImageType must have a second string that is "PRIMARY" or "SECONDARY"'
                                        ))
                except Exception:
                    findings.add(ValidationFinding(
                        file=potential_file, value='Non-text', tag=self.tag, description=f'ImageType has non-text values'
                    ))
        else:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='ImageOrientationPatient tag is missing'
            ))
        return findings


class SpecialExceptionFor_MR_ImageTypeValidator(RegexValidator):
    '''A validator that checks the ImageType tag for localizer images.

    This is a special case in the spreadsheet for the `mr_loc_v1` profile only where the image type can be
    the single word "LOCALIZER".
    '''

    description = 'ImageType for localizer images must be "LOCALIZER"'
    tag = pydicom.tag.Tag((0x0008, 0x0008))
    regex = re.compile(r'^LOCALIZER$')


# Lesion and Slice Details
# ------------------------

class SliceThicknessValidator(RegexValidator):
    '''A validator that checks the SliceThickness tag.'''

    description = 'SliceThickness must be a positive number, floating point or integer'
    tag = pydicom.tag.Tag((0x0018, 0x0050))
    regex = re.compile(r'^([1-9]\d*(\.\d+)?|0\.\d+)$')


# Image Spatial Information
# -------------------------

class FrameOfReferenceUIDValidator(DICOMUIDValidator):
    '''A validator that checks the FrameOfReferenceUID tag.'''

    description = 'FrameOfReferenceUID must be a valid DICOM UID of digits and dots; at least one dot, no leading/trailing dots; up to 64 characters'
    tag = pydicom.tag.Tag((0x0020, 0x0052))
