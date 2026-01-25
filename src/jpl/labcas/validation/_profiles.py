# encoding: utf-8

'''🛂 EDRN DICOM Validation: profiles.'''

from enum import Enum
from ._classes import Validator
from ._files import PotentialFile
from ._findings import Finding, WarningFinding
import logging

_logger = logging.getLogger(__name__)


class ProfileName(Enum):
    '''The name of a profile.'''
    NULL    = 'null'     # No-op or null profile that does no validation at all
    CT_LOC  = 'ct-loc'   # CT localizer / scout images
    CT_STD  = 'ct-std'   # CT standard images
    MR_LOC  = 'mr-loc'   # MR localizer images
    MR_STD  = 'mr-std'   # MR standard images
    PET_STD = 'pet-std'  # PET images
    SC      = 'sc'       # Secondary Capture
    SEG     = 'seg'      # Segmentation objects
    GENERIC = 'generic'  # Generic profile for when nothing else applies


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
        return list[Finding](sorted(findings))   


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

# For CT_STD, MR_STD, and PET_STD the validators are the same and they're all required, so
# let's collect them here in a single list and use them for all these profiles.
_all_required_validators = [
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
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
    validators.StudyDateValidator(),
    validators.ContentDateValidator(),
    validators.AcquisitionDateValidator(),
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

register_profile(Profile(ProfileName.CT_STD, _all_required_validators, []))
# MR_STD is identical to CT_STD — why even bother with separate profiles? Ask @hoodriverheather.
register_profile(Profile(ProfileName.MR_STD, _all_required_validators, []))
# PET_STD is identical to CT_STD and MR_STD
register_profile(Profile(ProfileName.PET_STD, _all_required_validators, []))


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
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
    validators.StudyDateValidator(),
    validators.ContentDateValidator(),
    validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.WindowCenterValidator(),
    validators.WindowWidthValidator(),
    validators.SliceThicknessValidator(),
    validators.PixelSpacingValidator(),
    validators.ImagePositionPatientValidator(),
    validators.ImageOrientationPatientValidator(),
]

register_profile(Profile(ProfileName.CT_LOC, _required_loc_validators, _optional_loc_validators,))
register_profile(Profile(ProfileName.MR_LOC, _required_loc_validators, _optional_loc_validators,))

# "Segmentation objects", whatever these are
register_profile(Profile(ProfileName.SEG, [
    validators.SOPClassUIDValidator(),    
    validators.ModalityValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.StudyInstanceUIDValidator(),
    validators.SeriesInstanceUIDValidator(),
    validators.SOPInstanceUIDValidator(),
    validators.RowsValidator(),
    validators.ColumnsValidator(),
], [
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
    validators.StudyDateValidator(),
    validators.ContentDateValidator(),
    validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.BitsAllocatedValidator(),
    validators.BitsStoredValidator(),
    validators.HighBitValidator(),
    validators.PixelRepresentationValidator(),
    validators.PhotometricInterpretationValidator(),
]))

# Secondary Capture, again, whatever thse are
register_profile(Profile(ProfileName.SC, [
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
], [
    validators.ImageTypeValidator(),
    validators.SeriesDescriptionValidator(),
    validators.FrameOfReferenceUIDValidator(),
    validators.SeriesNumberValidator(),
    validators.InstanceNumberValidator(),
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
    validators.StudyDateValidator(),
    validators.ContentDateValidator(),
    validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
]))

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
    validators.ManufacturerValidator(),
    validators.ModelNameValidator(),
    validators.SoftwareVersionsValidator(),
    validators.StudyDateValidator(),
    validators.ContentDateValidator(),
    validators.AcquisitionDateValidator(),
    validators.AcquisitionTimeValidator(),
    validators.ContentTimeValidator(),
    validators.WindowCenterValidator(),
    validators.WindowWidthValidator(),
    validators.SliceThicknessValidator(),
    validators.PixelSpacingValidator(),
    validators.ImagePositionPatientValidator(),
    validators.ImageOrientationPatientValidator(),
]))
