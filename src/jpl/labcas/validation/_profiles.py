# encoding: utf-8

'''🛂 EDRN DICOM Validation: profiles.

These valdation profiles are defined in "the spreadsheet", specifically the "SOP Class UID Routing" tab
to determine which sets of validators go where, and then the "CORE DICOM TAGS (MR & CT)" tab that
actually defines the validators themselves.

See:

https://docs.google.com/spreadsheets/d/1oQB0EoeajxFagSrIzF_8hOIc6hbC9MiMvhbYLfr6vPQ/edit?pli=1&gid=1779958583#gid=1779958583
'''

from enum import Enum
from ._classes import Validator
from ._files import PotentialFile
from ._findings import Finding, WarningFinding
import logging

_logger = logging.getLogger(__name__)


class ProfileName(Enum):
    '''The name of a profile.'''
    NULL               = 'null'
    CT_LOC             = 'CT localizer'
    CT_LOC_NEW         = 'CT localizer (for new data)'
    CT_STD             = 'CT standard'
    CT_STD_NEW         = 'CT standard (for new data)'
    MR_LOC             = 'MR localizer'
    MR_LOC_NEW         = 'MR localizer (for new data)'
    MR_STD             = 'MR standard'
    MR_STD_NEW         = 'MR standard (for new data)'
    PET_STD            = 'PET standard'
    PET_STD_NEW        = 'PET standard (for new data)'
    CT_DER             = 'CT derived or post-processed'
    CT_DER_NEW         = 'CT derived or post-processed (for new data)'
    MR_DER             = 'MR derived or post-processed'
    MR_DER_NEW         = 'MR derived or post-processed (for new data)'
    SC                 = 'Secondary capture'
    SC_NEW             = 'Secondary capture (for new data)'
    SEG                = 'Segmentation objects'
    SEG_NEW            = 'Segmentation objects (for new data)'
    GENERIC            = 'Generic'
    MISSING_IMAGE_TYPE = 'Missing ImageType'


class Profile:
    '''A "profile" is a set of validators to apply to subsets of DICOM files depending on their contents.'''

    def __init__(self, name: ProfileName, required_validators: list[Validator], optional_validators: list[Validator]):
        '''Initialize the profile with the given name and validators.'''
        self.name: ProfileName = name
        self.required_validators = required_validators
        self.optional_validators = optional_validators

    def validate(self, potential_file: PotentialFile) -> list[Finding]:
        '''Validate the given DICOM dataset `potential_file` against our profile and return the findings.'''
        findings: set[Finding] = set()
        for validator in self.required_validators:
            findings.update(validator.validate(potential_file))
        for validator in self.optional_validators:
            optional_findings = validator.validate(potential_file)
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

from . import validators
register_profile(Profile(ProfileName.NULL, [], []))

_all_ct_required_validators = [
    validators.SOPClassUIDValidator(),
    validators.ModalityValidator(),
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    # @hoodriverheather says in #31 to waive Manufacturer, ModelName, and SoftwareVersions for old data
    # validators.ManufacturerValidator(),
    # validators.ModelNameValidator(),
    # validators.SoftwareVersionsValidator(),
    # @hoodriverheather says in #31 to waive StudyDate, ContentDate, and AcquisitionDate for ALL data
    # validators.StudyDateValidator(),
    # validators.ContentDateValidator(),
    # validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),
    validators.WindowCenterValidator(),
    validators.WindowWidthValidator(),
    validators.SliceThicknessValidator(),
    validators.PixelSpacingValidator(),
    validators.ImagePositionPatientValidator(),
    validators.ImageOrientationPatientValidator(),
]
_all_ct_required_validators_for_new_data = _all_ct_required_validators + [
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
]
register_profile(Profile(ProfileName.CT_STD, _all_ct_required_validators, []))
register_profile(Profile(ProfileName.CT_STD_NEW, _all_ct_required_validators_for_new_data, []))

_all_mr_required_validators = [
    validators.SOPClassUIDValidator(),
    validators.ModalityValidator(),
    validators.MisterImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    # @hoodriverheather says in #31 to waive Manufacturer, ModelName, and SoftwareVersions for old data
    # validators.ManufacturerValidator(),
    # validators.ModelNameValidator(),
    # validators.SoftwareVersionsValidator(),
    # @hoodriverheather says in #31 to waive StudyDate, ContentDate, and AcquisitionDate for ALL data
    # validators.StudyDateValidator(),
    # validators.ContentDateValidator(),
    # validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),
    validators.WindowCenterValidator(),
    validators.WindowWidthValidator(),
    validators.SliceThicknessValidator(),
    validators.PixelSpacingValidator(),
    validators.ImagePositionPatientValidator(),
    validators.ImageOrientationPatientValidator(),
]
_all_mr_required_validators_for_new_data = _all_mr_required_validators + [
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
]

register_profile(Profile(ProfileName.MR_STD, _all_mr_required_validators, []))
register_profile(Profile(ProfileName.MR_STD_NEW, _all_mr_required_validators_for_new_data, []))

# LOC validators are the same for CT and MR, so collect them so we can reuse them in both profiles
_required_loc_validators = [
    validators.SOPClassUIDValidator(),
    validators.ModalityValidator(),
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),    
]
_optional_loc_validators = [
    validators.FrameOfReferenceUIDValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    # @hoodriverheather says in EDRN/jpl.labcas.validation#31 to waive Manufacturer, ModelName, and SoftwareVersions for old data
    # validators.ManufacturerValidator(),
    # validators.ModelNameValidator(),
    # validators.SoftwareVersionsValidator(),
    # @hoodriverheather says in #31 to waive StudyDate, ContentDate, and AcquisitionDate for ALL data
    # validators.StudyDateValidator(),
    # validators.ContentDateValidator(),
    # validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.WindowCenterValidator(),
    validators.WindowWidthValidator(),
    validators.SliceThicknessValidator(),
    validators.PixelSpacingValidator(),
    validators.ImagePositionPatientValidator(),
    validators.ImageOrientationPatientValidator(),
]
_optional_loc_validators_for_new_data = _optional_loc_validators + [
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
]

register_profile(Profile(ProfileName.CT_LOC, _required_loc_validators, _optional_loc_validators,))
register_profile(Profile(ProfileName.MR_LOC, _required_loc_validators, _optional_loc_validators,))
register_profile(Profile(ProfileName.CT_LOC_NEW, _required_loc_validators, _optional_loc_validators_for_new_data,))
register_profile(Profile(ProfileName.MR_LOC_NEW, _required_loc_validators, _optional_loc_validators_for_new_data,))

# PET_STD is similar to CT_STD and MR_STD … but has 3 different optional validators
_pet_std_validators = [
    validators.SOPClassUIDValidator(),
    validators.ModalityValidator(),
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    # @hoodriverheather says in EDRN/jpl.labcas.validation#31 to waive Manufacturer, ModelName, and SoftwareVersions
    # validators.ManufacturerValidator(),
    # validators.ModelNameValidator(),
    # validators.SoftwareVersionsValidator(),
    # @hoodriverheather says in #31 to waive StudyDate, ContentDate, and AcquisitionDate for ALL data
    # validators.StudyDateValidator(),
    # validators.ContentDateValidator(),
    # validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),
    validators.PixelSpacingValidator(),
    validators.ImagePositionPatientValidator(),
    validators.ImageOrientationPatientValidator(),

]
_pet_std_validators_for_new_data = _pet_std_validators + [
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
]
_pet_std_optional_validators = [
    validators.WindowCenterValidator(),
]
register_profile(Profile(ProfileName.PET_STD, _pet_std_validators, _pet_std_optional_validators))
register_profile(Profile(ProfileName.PET_STD_NEW, _pet_std_validators_for_new_data, _pet_std_optional_validators))


# "Segmentation objects", whatever these are
_required_seg_validators = [
    validators.SOPClassUIDValidator(),    
    validators.ModalityValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
]
_optional_seg_validators = [
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    # @hoodriverheather says in EDRN/jpl.labcas.validation#31 to waive Manufacturer, ModelName, and SoftwareVersions
    # validators.ManufacturerValidator(),
    # validators.ModelNameValidator(),
    # validators.SoftwareVersionsValidator(),
    # @hoodriverheather says in #31 to waive StudyDate, ContentDate, and AcquisitionDate for ALL data
    # validators.StudyDateValidator(),
    # validators.ContentDateValidator(),
    # validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),
]
_optional_seg_validators_for_new_data = _optional_seg_validators + [
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
]
register_profile(Profile(ProfileName.SEG, _required_seg_validators, _optional_seg_validators))
register_profile(Profile(ProfileName.SEG_NEW, _required_seg_validators, _optional_seg_validators_for_new_data))

# Secondary Capture, again, whatever thse are
_required_sc_validators = [
    validators.SOPClassUIDValidator(),
    validators.ModalityValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),    
    validators.WindowCenterValidator(),
    validators.WindowWidthValidator(),
]
_optional_sc_validators = [
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    # @hoodriverheather says in EDRN/jpl.labcas.validation#31 to waive Manufacturer, ModelName, and SoftwareVersions
    # validators.ManufacturerValidator(),
    # validators.ModelNameValidator(),
    # validators.SoftwareVersionsValidator(),
    # @hoodriverheather says in #31 to waive StudyDate, ContentDate, and AcquisitionDate for ALL data
    # validators.StudyDateValidator(),
    # validators.ContentDateValidator(),
    # validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.ImagePositionPatientValidator(),
]
_optional_sc_validators_for_new_data = _optional_sc_validators + [
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
]
register_profile(Profile(ProfileName.SC, _required_sc_validators, _optional_sc_validators))
register_profile(Profile(ProfileName.SC_NEW, _required_sc_validators, _optional_sc_validators_for_new_data))

register_profile(Profile(ProfileName.GENERIC, [
    validators.SOPClassUIDValidator(),
    validators.ModalityValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),
], [
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    # @hoodriverheather says in EDRN/jpl.labcas.validation#31 to waive Manufacturer, ModelName, and SoftwareVersions
    # validators.ManufacturerValidator(),
    # validators.ModelNameValidator(),
    # validators.SoftwareVersionsValidator(),
    # @hoodriverheather says in #31 to waive StudyDate, ContentDate, and AcquisitionDate for ALL data
    # validators.StudyDateValidator(),
    # validators.ContentDateValidator(),
    # validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.WindowCenterValidator(),
    validators.WindowWidthValidator(),
    validators.SliceThicknessValidator(),
    validators.PixelSpacingValidator(),
    validators.ImagePositionPatientValidator(),
    validators.ImageOrientationPatientValidator(),
]))


# Derrrr-profiles; from "the spreadsheet", these are identical to each other,
# so we'll collect the validators once and then register them for both der profiles.

_required_der_validators = [
    validators.SOPClassUIDValidator(),
    validators.ModalityValidator(),
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    # @hoodriverheather says in EDRN/jpl.labcas.validation#31 to waive Manufacturer, ModelName, and SoftwareVersions
    # validators.ManufacturerValidator(),
    # validators.ModelNameValidator(),
    # validators.SoftwareVersionsValidator(),
    # @hoodriverheather says in #31 to waive StudyDate, ContentDate, and AcquisitionDate for ALL data
    # validators.StudyDateValidator(),
    # validators.ContentDateValidator(),
    # validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),
]
_optional_der_validators = [
    validators.WindowCenterValidator(),
    validators.WindowWidthValidator(),
    validators.SliceThicknessValidator(),
    validators.PixelSpacingValidator(),
    validators.ImagePositionPatientValidator(),
    validators.ImageOrientationPatientValidator(),
]
_required_der_validators_for_new_data = _required_der_validators + [
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
]
register_profile(Profile(ProfileName.CT_DER, _required_der_validators, _optional_der_validators))
register_profile(Profile(ProfileName.MR_DER, _required_der_validators, _optional_der_validators))
register_profile(Profile(ProfileName.CT_DER_NEW, _required_der_validators_for_new_data, _optional_der_validators))
register_profile(Profile(ProfileName.MR_DER_NEW, _required_der_validators_for_new_data, _optional_der_validators))