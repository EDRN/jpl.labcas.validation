# encoding: utf-8

'''🛂 EDRN DICOM Validation: validators.'''


from ._experimental import (
    ExperimentalModalityValidator, ExperimentalManufacturerValidator, ExperimentalWarningValidator  # noqa: F401
)
from ._core import (  # noqa: F401
    AcquisitionDateValidator,
    AcquisitionTimeValidator,
    BitsAllocatedValidator,
    BitsStoredValidator,
    ColumnsValidator,
    ContentDateValidator,
    ContentTimeValidator,
    FrameOfReferenceUIDValidator,
    HighBitValidator,
    ImageOrientationPatientValidator,
    ImagePositionPatientValidator,
    ImageTypeValidator,
    InstanceNumberValidator,
    ManufacturerValidator,
    ModalityValidator,
    ModelNameValidator,
    PhotometricInterpretationValidator,
    PixelRepresentationValidator,
    PixelSpacingValidator,
    RowsValidator,
    SeriesDescriptionValidator,
    SeriesInstanceUIDValidator,
    SeriesNumberValidator,
    SliceThicknessValidator,
    SoftwareVersionsValidator,
    SOPClassUIDValidator,
    SOPInstanceUIDValidator,
    SpecialExceptionFor_MR_ImageTypeValidator,
    StudyDateValidator,
    StudyInstanceUIDValidator,
    WindowCenterValidator,
    WindowWidthValidator,

)
from ._mr import (  # noqa: F401
    SpacingBetweenSlicesValidator, AcquisitionMatrixValidator, MisterImageTypeValidator,
    DiffusionBValueValidator,
)

from ._ct import (  # noqa: F401
    ExposureTimeValidator,
    XRayTubeCurrentValidator,
    ExposureValidator,
    CTDIvolValidator,
    CTDIPhantomTypeCodeSequenceValidator,
    RescaleSlopeValidator,
    RescaleInterceptValidator,
)

from ._pet import (  # noqa: F401
    PatientWeightValidator,
    RadiopharmaceuticalInformationSequenceValidator,
    RadionuclideCodeSequenceValidator,
    RadionuclideTotalDoseValidator,
    RadionuclideHalfLifeValidator,
    RadiopharmaceuticalStartTimeDateTimeValidator,
    DecayCorrectionValidator,
)

from ._rtstruct import (  # noqa: F401
    StructureSetLabelValidator,
    StructureSetNameValidator,
    StructureSetDescriptionValidator,
    ReferencedFrameOfReferenceSequenceValidator,
    StructureSetROISequenceValidator,
    ROIContourSequenceValidator,
    RTROIObservationsSequenceValidator,
)

__all__ = [
    'ExperimentalModalityValidator', 'ExperimentalManufacturerValidator', 'ExperimentalWarningValidator',
    'AcquisitionDateValidator',
    'AcquisitionTimeValidator',
    'BitsAllocatedValidator',
    'BitsStoredValidator',
    'ColumnsValidator',
    'ContentDateValidator',
    'ContentTimeValidator',
    'FrameOfReferenceUIDValidator',
    'HighBitValidator',
    'ImageOrientationPatientValidator',
    'ImagePositionPatientValidator',
    'ImageTypeValidator',
    'InstanceNumberValidator',
    'ManufacturerValidator',
    'MisterImageTypeValidator',
    'ModalityValidator',
    'ModelNameValidator',
    'PhotometricInterpretationValidator',
    'PixelRepresentationValidator',
    'PixelSpacingValidator',
    'RowsValidator',
    'SeriesDescriptionValidator',
    'SeriesInstanceUIDValidator',
    'SeriesNumberValidator',
    'SliceThicknessValidator',
    'SoftwareVersionsValidator',
    'SOPClassUIDValidator',
    'SOPInstanceUIDValidator',
    'SpecialExceptionFor_MR_ImageTypeValidator',
    'StudyDateValidator',
    'StudyInstanceUIDValidator',
    'WindowCenterValidator',
    'WindowWidthValidator',
    # @hoodriverheather's so-called 'MR Extensions':
    'SpacingBetweenSlicesValidator', 'AcquisitionMatrixValidator', 'DiffusionBValueValidator',
    # @hoodriverheather's 'CT Extensions':
    'ExposureTimeValidator', 'XRayTubeCurrentValidator', 'ExposureValidator', 'CTDIvolValidator',
    'CTDIPhantomTypeCodeSequenceValidator', 'RescaleSlopeValidator', 'RescaleInterceptValidator',
    # @hoodriverheather's 'PET Extensions':
    'PatientWeightValidator', 'RadiopharmaceuticalInformationSequenceValidator',
    'RadionuclideCodeSequenceValidator', 'RadionuclideTotalDoseValidator', 'RadionuclideHalfLifeValidator',
    'RadiopharmaceuticalStartTimeDateTimeValidator', 'DecayCorrectionValidator',
    # RT Struct extensions:
    'StructureSetLabelValidator', 'StructureSetNameValidator', 'StructureSetDescriptionValidator',
    'ReferencedFrameOfReferenceSequenceValidator', 'StructureSetROISequenceValidator',
    'ROIContourSequenceValidator', 'RTROIObservationsSequenceValidator',
]
