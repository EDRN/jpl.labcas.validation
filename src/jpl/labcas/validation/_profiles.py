# encoding: utf-8

'''🛂 EDRN DICOM Validation: profiles.

These valdation profiles are defined in "the spreadsheet", specifically the "SOP Class UID Routing" tab
to determine which sets of validators go where, and then the "CORE DICOM TAGS (MR & CT)" tab that
actually defines the validators themselves.

See:

https://docs.google.com/spreadsheets/d/1MPSEOMTVnT-eVL8AXLXVebuBOqNDSxrz_cqAV1az_N4/edit?gid=1392488545#gid=1392488545
'''

from enum import Enum
from ._classes import Validator
from ._files import PotentialFile
from ._findings import Finding, WarningFinding
import humanize, logging

_logger = logging.getLogger(__name__)


class ProfileName(Enum):
    '''The name of a profile.'''
    NULL                = 'null'
    CT_LOC              = 'CT localizer'
    CT_LOC_NEW          = 'CT localizer (for new data)'
    CT_STD              = 'CT standard'
    CT_STD_NEW          = 'CT standard (for new data)'
    MR_LOC              = 'MR localizer'
    MR_LOC_NEW          = 'MR localizer (for new data)'
    MR_STD              = 'MR standard'
    MR_STD_NEW          = 'MR standard (for new data)'
    PET_STD             = 'PET standard'
    PET_STD_NEW         = 'PET standard (for new data)'
    CT_DER              = 'CT derived or post-processed'
    CT_DER_NEW          = 'CT derived or post-processed (for new data)'
    MR_DER              = 'MR derived or post-processed'
    MR_DER_NEW          = 'MR derived or post-processed (for new data)'
    SC                  = 'Secondary capture'
    SC_NEW              = 'Secondary capture (for new data)'
    SEG                 = 'Segmentation objects'
    SEG_NEW             = 'Segmentation objects (for new data)'
    NON_IMAGE_DICOM     = 'Non-image DICOM'
    NON_IMAGE_DICOM_NEW = 'Non-image DICOM (for new data)'
    RTSTRUCT            = 'RT Struct'
    RTSTRUCT_NEW        = 'RT Struct (for new data)'
    OTHER_IMAGE         = 'Other image'
    OTHER_IMAGE_NEW     = 'Other image (for new data)'
    GENERIC             = 'Generic'
    MISSING_IMAGE_TYPE  = 'Missing ImageType'


class Profile:
    '''A "profile" is a set of validators to apply to subsets of DICOM files depending on their contents.'''

    def __init__(
        self, name: ProfileName, alias: str | None, minimum_file_size: int,
        required_validators: list[Validator], optional_validators: list[Validator]
    ):
        '''Initialize the profile with the given name and validators.'''
        self.name: ProfileName = name
        self.alias = alias if alias else 'N/A'
        self.minimum_file_size = minimum_file_size
        self.required_validators = required_validators
        self.optional_validators = optional_validators

    def validate(self, potential_file: PotentialFile) -> list[Finding]:
        '''Validate the given DICOM dataset `potential_file` against our profile and return the findings.'''
        findings: set[Finding] = set()
        for validator in self.required_validators:
            findings.update(validator.validate(potential_file))
        for validator in self.optional_validators:
            try:
                optional_findings = validator.validate(potential_file)
            except Exception as ex:
                _logger.error('🤷 Error validating optional validator %s: %s', validator, ex)
                breakpoint()
            for finding in optional_findings:
                if finding.kind() != '👮 Warning':
                    # Convert to WarningFinding by copying attributes
                    tag = finding.tag if hasattr(finding, 'tag') else None
                    description = finding.description if hasattr(finding, 'description') else None
                    finding = WarningFinding(
                        file=finding.file,
                        value=finding.value,
                        score=finding.score,
                        tag=tag,
                        description=description
                    )
                findings.add(finding)
        return sorted(list[Finding](findings))
    
    def __str__(self) -> str:
        rc = f'### `{self.name}`\n\n'
        minimum_file_size = humanize.naturalsize(self.minimum_file_size, binary=True)
        rc += f"Alias from Heather's spreadsheet: {self.alias}\n\nMinimum file size: {minimum_file_size}\n\nRequired validators:\n\n"
        if not self.required_validators:
            rc += 'None defined\n'
        else:
            for validator in self.required_validators:
                rc += f'- {validator}\n'
        rc += '\n\nOptional validators:\n\n'
        if not self.optional_validators:
            rc += 'None defined\n'
        else:
            for validator in self.optional_validators:
                rc += f'- {validator}\n'
        return rc

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(name={self.name})'


def register_profile(p: Profile):
    global PROFILES
    PROFILES[p.name] = p


def get_profile(profile_name: ProfileName) -> Profile:
    global PROFILES
    if profile_name not in PROFILES:
        _logger.warning('🤷 Unknown profile name «%s», falling back to generic profile', profile_name)
        profile_name = ProfileName.GENERIC
    return PROFILES[profile_name]

PROFILES: dict[ProfileName, Profile] = {}

DEFAULT_MINIMUM_FILE_SIZE = int(7.5 * 1024)
NO_MINIMUM_FILE_SIZE = 0

from .validators import *  # noqa: F403
register_profile(Profile(ProfileName.NULL, None, DEFAULT_MINIMUM_FILE_SIZE, [], []))

register_profile(Profile(ProfileName.CT_STD, 'ct_std_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelSpacingValidator(),
    PhotometricInterpretationValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelRepresentationValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    CTDIvolValidator(),
    RescaleInterceptValidator(),
    RescaleSlopeValidator(),
], [
    SeriesDescriptionValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    ExposureValidator(),
    CTDIPhantomTypeCodeSequenceValidator(),
    ExposureTimeValidator(),
    XRayTubeCurrentValidator(),
]))

register_profile(Profile(ProfileName.CT_STD_NEW, 'ct_std_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    CTDIvolValidator(),
    RescaleInterceptValidator(),
    RescaleSlopeValidator(),
], [
    ExposureValidator(),
    CTDIPhantomTypeCodeSequenceValidator(),
    ExposureTimeValidator(),
    XRayTubeCurrentValidator(),
]))

register_profile(Profile(ProfileName.MR_STD, 'mr_std_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    SpacingBetweenSlicesValidator(),
    AcquisitionMatrixValidator(),
], [
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    DiffusionBValueValidator(),
]))

register_profile(Profile(ProfileName.MR_STD_NEW, 'mr_std_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    SpacingBetweenSlicesValidator(),
    AcquisitionMatrixValidator(),
], [
    DiffusionBValueValidator(),
]))

register_profile(Profile(ProfileName.CT_LOC, 'ct_loc_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
    RescaleInterceptValidator(),
    RescaleSlopeValidator()
], [
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    ExposureValidator(),
    CTDIvolValidator(),
    CTDIPhantomTypeCodeSequenceValidator(),
    ExposureTimeValidator(),
    XRayTubeCurrentValidator(),
]))

register_profile(Profile(ProfileName.MR_LOC, 'mr_loc_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    SeriesDescriptionValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    SpecialExceptionFor_MR_ImageTypeValidator(),
    FrameOfReferenceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    SpacingBetweenSlicesValidator(),
    AcquisitionMatrixValidator(),
]))

register_profile(Profile(ProfileName.CT_LOC_NEW, 'ct_loc_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
    RescaleInterceptValidator(),
    RescaleSlopeValidator(),
], [
    FrameOfReferenceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    ExposureValidator(),
    CTDIvolValidator(),
    CTDIPhantomTypeCodeSequenceValidator(),
    ExposureTimeValidator(),
    XRayTubeCurrentValidator(),
]))


register_profile(Profile(ProfileName.MR_LOC_NEW, 'mr_loc_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    FrameOfReferenceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    SpacingBetweenSlicesValidator(),
    AcquisitionMatrixValidator(),
]))

register_profile(Profile(ProfileName.PET_STD, 'pet_std_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    PatientWeightValidator(),
    RadiopharmaceuticalInformationSequenceValidator(),
    DecayCorrectionValidator(),
], [
    SeriesDescriptionValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
]))

register_profile(Profile(ProfileName.PET_STD_NEW, 'pet_std_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    PatientWeightValidator(),
    RadiopharmaceuticalInformationSequenceValidator(),
    DecayCorrectionValidator(),
], [
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
]))

register_profile(Profile(ProfileName.SEG, 'seg_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
], [
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
]))

register_profile(Profile(ProfileName.SEG_NEW, 'seg_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
], [
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
]))

register_profile(Profile(ProfileName.SC, 'sc_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
]))


register_profile(Profile(ProfileName.SC_NEW, 'sc_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
]))

register_profile(Profile(ProfileName.CT_DER, 'ct_der_post_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    SeriesDescriptionValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    RescaleInterceptValidator(),
    RescaleSlopeValidator(),
]))


register_profile(Profile(ProfileName.MR_DER, 'mr_der_post_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    DiffusionBValueValidator(),
]))


register_profile(Profile(ProfileName.CT_DER_NEW, 'ct_der_post_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    RescaleInterceptValidator(),
    RescaleSlopeValidator(),
]))

register_profile(Profile(ProfileName.MR_DER_NEW, 'mr_der_post_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    ImageTypeValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    AcquisitionTimeValidator(),
    ContentTimeValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    WindowCenterValidator(),
    WindowWidthValidator(),
    SliceThicknessValidator(),
    PixelSpacingValidator(),
    ImagePositionPatientValidator(),
    ImageOrientationPatientValidator(),
    DiffusionBValueValidator(),
]))

register_profile(Profile(ProfileName.NON_IMAGE_DICOM, 'non_image_dicom_v1', NO_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    SOPInstanceUIDValidator(),
], [
    SeriesDescriptionValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
]))

register_profile(Profile(ProfileName.NON_IMAGE_DICOM_NEW, 'non_image_dicom_v2', NO_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
], [
    SeriesDescriptionValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
]))

register_profile(Profile(ProfileName.OTHER_IMAGE, 'other_image_v1', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    SOPInstanceUIDValidator(),
], [
    SeriesDescriptionValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
]))

register_profile(Profile(ProfileName.OTHER_IMAGE_NEW, 'other_image_v2', DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    SeriesDescriptionValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    ManufacturerValidator(),
    SoftwareVersionsValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], [
    ModelNameValidator(),
    WindowCenterValidator(),
    WindowWidthValidator(),
]))

register_profile(Profile(ProfileName.GENERIC, None, DEFAULT_MINIMUM_FILE_SIZE, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    RowsValidator(),
    ColumnsValidator(),
    BitsAllocatedValidator(),
    BitsStoredValidator(),
    HighBitValidator(),
    PixelRepresentationValidator(),
    PhotometricInterpretationValidator(),
], []))

register_profile(Profile(ProfileName.RTSTRUCT, 'rtstruct_v1', 0, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    StructureSetLabelValidator(),
    ReferencedFrameOfReferenceSequenceValidator(),
    StructureSetROISequenceValidator(),
    ROIContourSequenceValidator(),
], [
    SeriesDescriptionValidator(),
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    StructureSetNameValidator(),
    StructureSetDescriptionValidator(),
    RTROIObservationsSequenceValidator(),
]))

register_profile(Profile(ProfileName.RTSTRUCT_NEW, 'rtstruct_v2', 0, [
    SOPClassUIDValidator(),
    ModalityValidator(),
    SeriesDescriptionValidator(),
    FrameOfReferenceUIDValidator(),
    StudyInstanceUIDValidator(),
    SeriesInstanceUIDValidator(),
    SOPInstanceUIDValidator(),
    ManufacturerValidator(),
    ModelNameValidator(),
    SoftwareVersionsValidator(),
    StructureSetLabelValidator(),
    ReferencedFrameOfReferenceSequenceValidator(),
    StructureSetROISequenceValidator(),
    ROIContourSequenceValidator(),
], [
    SeriesNumberValidator(),
    InstanceNumberValidator(),
    StructureSetNameValidator(),
    StructureSetDescriptionValidator(),
    RTROIObservationsSequenceValidator(),
]))
