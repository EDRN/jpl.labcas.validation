# encoding: utf-8

'''🛂 EDRN DICOM Validation: RTSTRUCT validators.'''

from ._base import RegexValidator, DICOMUIDValidator
from .._classes import Validator
from .._files import PotentialFile
from .._findings import ValidationFinding
from pydicom.dataelem import DataElement, convert_raw_data_element
from pydicom.sequence import Sequence as DICOMSequence
import pydicom, re


_non_empty_text = re.compile(r'.+')
_positive_integer = re.compile(r'^[1-9]\d*$')
_roi_number = re.compile(r'^[0-9]+$')

_frame_of_reference_uid_tag = pydicom.tag.Tag((0x0020, 0x0052))
_rt_referenced_study_sequence_tag = pydicom.tag.Tag((0x3006, 0x0012))
_rt_referenced_series_sequence_tag = pydicom.tag.Tag((0x3006, 0x0014))
_contour_image_sequence_tag = pydicom.tag.Tag((0x3006, 0x0016))
_referenced_sop_class_uid_tag = pydicom.tag.Tag((0x0008, 0x1150))
_referenced_sop_instance_uid_tag = pydicom.tag.Tag((0x0008, 0x1155))
_roi_number_tag = pydicom.tag.Tag((0x3006, 0x0022))
_roi_name_tag = pydicom.tag.Tag((0x3006, 0x0026))
_referenced_roi_number_tag = pydicom.tag.Tag((0x3006, 0x0084))
_contour_sequence_tag = pydicom.tag.Tag((0x3006, 0x0040))
_contour_geometric_type_tag = pydicom.tag.Tag((0x3006, 0x0042))
_number_of_contour_points_tag = pydicom.tag.Tag((0x3006, 0x0046))
_contour_data_tag = pydicom.tag.Tag((0x3006, 0x0050))

_valid_contour_geometric_types = frozenset({
    'POINT', 'OPEN_PLANAR', 'OPEN_NONPLANAR', 'CLOSED_PLANAR', 'CLOSEDPLANAR_XOR',
})
_uid_regex = DICOMUIDValidator.regex


def _get_sequence(ds: pydicom.Dataset, tag: pydicom.tag.Tag) -> DICOMSequence | None:
    '''Return a converted sequence value from the dataset, or None if absent.'''
    elem = ds.get_item(tag)
    if elem is None:
        return None
    if not isinstance(elem, DataElement):
        elem = convert_raw_data_element(elem)
    value = elem.value
    return value if isinstance(value, DICOMSequence) else None


def _non_empty_str(value) -> str | None:
    '''Return a stripped string when non-empty, otherwise None.'''
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _validate_uid(findings: set[ValidationFinding], potential_file: PotentialFile, tag: pydicom.tag.Tag, value, description: str):
    '''Add a finding when a UID value is missing or invalid.'''
    s = _non_empty_str(value)
    if s is None:
        findings.add(ValidationFinding(
            file=potential_file, value='value missing', tag=tag, description=description,
        ))
    elif not _uid_regex.match(s):
        findings.add(ValidationFinding(
            file=potential_file, value=s, tag=tag, description=description,
        ))


class StructureSetLabelValidator(RegexValidator):
    '''A validator that checks the StructureSetLabel tag.'''

    description = 'Structure Set Label must be present and non-empty (DICOM text value; no blank or placeholder-only values)'
    tag = pydicom.tag.Tag((0x3006, 0x0002))
    regex = _non_empty_text


class StructureSetNameValidator(RegexValidator):
    '''A validator that checks the StructureSetName tag when present.'''

    description = 'Structure Set Name, if present, should be non-empty and meaningful (DICOM text value)'
    tag = pydicom.tag.Tag((0x3006, 0x0004))
    regex = _non_empty_text


class StructureSetDescriptionValidator(RegexValidator):
    '''A validator that checks the StructureSetDescription tag when present.'''

    description = 'Structure Set Description, if present, should be non-empty and meaningful (DICOM text value)'
    tag = pydicom.tag.Tag((0x3006, 0x0006))
    regex = _non_empty_text


class ReferencedFrameOfReferenceSequenceValidator(Validator):
    '''A validator that checks the Referenced Frame of Reference Sequence and nested references.'''

    description = (
        'Referenced Frame of Reference Sequence must be present with at least one Item; '
        'each Item must include Frame of Reference UID and connect to referenced study, series, '
        'and contour image instances with valid Referenced SOP Class UID and Referenced SOP Instance UID values'
    )
    tag = pydicom.tag.Tag((0x3006, 0x0010))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        sequence = _get_sequence(ds, self.tag)
        if sequence is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='Referenced Frame of Reference Sequence must be present with at least one Item',
            ))
            return findings
        if len(sequence) < 1:
            findings.add(ValidationFinding(
                file=potential_file, value=len(sequence), tag=self.tag,
                description='Referenced Frame of Reference Sequence must contain at least one Item',
            ))
            return findings

        for rfor_index, rfor_item in enumerate(sequence):
            _validate_uid(
                findings, potential_file, _frame_of_reference_uid_tag,
                getattr(rfor_item, 'FrameOfReferenceUID', None),
                'Referenced Frame of Reference Sequence Item must include a valid Frame of Reference UID',
            )

            study_sequence = getattr(rfor_item, 'RTReferencedStudySequence', None)
            if not isinstance(study_sequence, DICOMSequence) or len(study_sequence) < 1:
                findings.add(ValidationFinding(
                    file=potential_file,
                    value=len(study_sequence) if isinstance(study_sequence, DICOMSequence) else study_sequence,
                    tag=_rt_referenced_study_sequence_tag,
                    description='RT Referenced Study Sequence must be present with at least one Item',
                ))
                continue

            for study_item in study_sequence:
                series_sequence = getattr(study_item, 'RTReferencedSeriesSequence', None)
                if not isinstance(series_sequence, DICOMSequence) or len(series_sequence) < 1:
                    findings.add(ValidationFinding(
                        file=potential_file,
                        value=len(series_sequence) if isinstance(series_sequence, DICOMSequence) else series_sequence,
                        tag=_rt_referenced_series_sequence_tag,
                        description='RT Referenced Series Sequence must be present with at least one Item',
                    ))
                    continue

                for series_item in series_sequence:
                    contour_image_sequence = getattr(series_item, 'ContourImageSequence', None)
                    if not isinstance(contour_image_sequence, DICOMSequence) or len(contour_image_sequence) < 1:
                        findings.add(ValidationFinding(
                            file=potential_file,
                            value=len(contour_image_sequence) if isinstance(contour_image_sequence, DICOMSequence) else contour_image_sequence,
                            tag=_contour_image_sequence_tag,
                            description='Contour Image Sequence must include references to the source image instances used for contours',
                        ))
                        continue

                    for image_item in contour_image_sequence:
                        _validate_uid(
                            findings, potential_file, _referenced_sop_class_uid_tag,
                            getattr(image_item, 'ReferencedSOPClassUID', None),
                            'Contour Image Sequence Item must include a valid Referenced SOP Class UID',
                        )
                        _validate_uid(
                            findings, potential_file, _referenced_sop_instance_uid_tag,
                            getattr(image_item, 'ReferencedSOPInstanceUID', None),
                            'Contour Image Sequence Item must include a valid Referenced SOP Instance UID',
                        )

        return findings


class StructureSetROISequenceValidator(Validator):
    '''A validator that checks the Structure Set ROI Sequence and nested ROI attributes.'''

    description = (
        'Structure Set ROI Sequence must be present with at least one ROI Item; '
        'each Item must include ROI Number and ROI Name, and ROI Numbers must be unique within the sequence'
    )
    tag = pydicom.tag.Tag((0x3006, 0x0020))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        sequence = _get_sequence(ds, self.tag)
        if sequence is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='Structure Set ROI Sequence must be present with at least one ROI Item',
            ))
            return findings
        if len(sequence) < 1:
            findings.add(ValidationFinding(
                file=potential_file, value=len(sequence), tag=self.tag,
                description='Structure Set ROI Sequence must contain at least one ROI Item',
            ))
            return findings

        seen_roi_numbers: set[str] = set()
        for item in sequence:
            roi_number = _non_empty_str(getattr(item, 'ROINumber', None))
            if roi_number is None or not _roi_number.match(roi_number):
                findings.add(ValidationFinding(
                    file=potential_file, value=getattr(item, 'ROINumber', None), tag=_roi_number_tag,
                    description='ROI Number is required for each Structure Set ROI Sequence Item and must be a non-empty integer string',
                ))
            elif roi_number in seen_roi_numbers:
                findings.add(ValidationFinding(
                    file=potential_file, value=roi_number, tag=_roi_number_tag,
                    description=f'ROI Number values must be unique within Structure Set ROI Sequence (duplicate {roi_number})',
                ))
            else:
                seen_roi_numbers.add(roi_number)

            roi_name = _non_empty_str(getattr(item, 'ROIName', None))
            if roi_name is None:
                findings.add(ValidationFinding(
                    file=potential_file, value=getattr(item, 'ROIName', None), tag=_roi_name_tag,
                    description='ROI Name is required for each Structure Set ROI Sequence Item and must be non-empty',
                ))

        return findings


class ROIContourSequenceValidator(Validator):
    '''A validator that checks the ROI Contour Sequence and nested contour geometry.'''

    description = (
        'ROI Contour Sequence must be present with at least one ROI contour Item; '
        'at least one Item must include Contour Sequence with non-empty contour geometry; '
        'each Contour Sequence Item must include Contour Geometric Type, Number of Contour Points, and Contour Data'
    )
    tag = pydicom.tag.Tag((0x3006, 0x0039))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        sequence = _get_sequence(ds, self.tag)
        if sequence is None:
            findings.add(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description='ROI Contour Sequence must be present with at least one ROI contour Item',
            ))
            return findings
        if len(sequence) < 1:
            findings.add(ValidationFinding(
                file=potential_file, value=len(sequence), tag=self.tag,
                description='ROI Contour Sequence must contain at least one ROI contour Item',
            ))
            return findings

        has_contour_geometry = False
        for roi_contour_item in sequence:
            referenced_roi_number = _non_empty_str(getattr(roi_contour_item, 'ReferencedROINumber', None))
            if referenced_roi_number is None:
                findings.add(ValidationFinding(
                    file=potential_file, value=getattr(roi_contour_item, 'ReferencedROINumber', None),
                    tag=_referenced_roi_number_tag,
                    description='Each ROI Contour Sequence Item should include Referenced ROI Number',
                ))

            contour_sequence = getattr(roi_contour_item, 'ContourSequence', None)
            if not isinstance(contour_sequence, DICOMSequence) or len(contour_sequence) < 1:
                continue

            has_contour_geometry = True
            for contour_item in contour_sequence:
                geometric_type = _non_empty_str(getattr(contour_item, 'ContourGeometricType', None))
                if geometric_type is None:
                    findings.add(ValidationFinding(
                        file=potential_file, value=getattr(contour_item, 'ContourGeometricType', None),
                        tag=_contour_geometric_type_tag,
                        description='Contour Geometric Type is required for each Contour Sequence Item',
                    ))
                elif geometric_type.upper() not in _valid_contour_geometric_types:
                    findings.add(ValidationFinding(
                        file=potential_file, value=geometric_type, tag=_contour_geometric_type_tag,
                        description='Contour Geometric Type must be a valid DICOM contour geometric type '
                        '(POINT, OPEN_PLANAR, OPEN_NONPLANAR, CLOSED_PLANAR, or CLOSEDPLANAR_XOR)',
                    ))

                number_of_points_raw = getattr(contour_item, 'NumberOfContourPoints', None)
                number_of_points = _non_empty_str(number_of_points_raw)
                if number_of_points is None or not _positive_integer.match(number_of_points):
                    findings.add(ValidationFinding(
                        file=potential_file, value=number_of_points_raw, tag=_number_of_contour_points_tag,
                        description='Number of Contour Points is required for each Contour Sequence Item and must be a positive integer',
                    ))
                    continue
                point_count = int(number_of_points)

                contour_data = getattr(contour_item, 'ContourData', None)
                if contour_data is None:
                    findings.add(ValidationFinding(
                        file=potential_file, value='value missing', tag=_contour_data_tag,
                        description='Contour Data is required for each Contour Sequence Item',
                    ))
                    continue

                if isinstance(contour_data, (str, bytes)):
                    data_values = [contour_data]
                else:
                    try:
                        data_values = list(contour_data)
                    except TypeError:
                        data_values = []

                if len(data_values) < 1:
                    findings.add(ValidationFinding(
                        file=potential_file, value='value missing', tag=_contour_data_tag,
                        description='Contour Data must contain contour coordinate values',
                    ))
                    continue

                if len(data_values) != point_count * 3:
                    findings.add(ValidationFinding(
                        file=potential_file, value=len(data_values), tag=_contour_data_tag,
                        description=(
                            f'Contour Data must contain {point_count * 3} coordinate values '
                            f'({point_count} x,y,z triplets) to match Number of Contour Points ({point_count})'
                        ),
                    ))

        if not has_contour_geometry:
            findings.add(ValidationFinding(
                file=potential_file, value='no contour geometry', tag=_contour_sequence_tag,
                description='At least one ROI Contour Sequence Item must include Contour Sequence with non-empty contour geometry',
            ))

        return findings


class RTROIObservationsSequenceValidator(Validator):
    '''A validator that checks the RT ROI Observations Sequence when present.'''

    description = 'RT ROI Observations Sequence, if present, should contain at least one observation Item'
    tag = pydicom.tag.Tag((0x3006, 0x0080))

    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        findings: set[ValidationFinding] = set()
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        sequence = _get_sequence(ds, self.tag)
        if sequence is None:
            return findings
        if len(sequence) < 1:
            findings.add(ValidationFinding(
                file=potential_file, value=len(sequence), tag=self.tag,
                description='RT ROI Observations Sequence must contain at least one Item when present',
            ))
        return findings
