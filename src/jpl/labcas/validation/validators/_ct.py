# encoding: utf-8

'''🛂 EDRN DICOM Validation: CT validators.'''

from ._base import RegexValidator
import pydicom, re


class ExposureTimeValidator(RegexValidator):
    '''A validator that checks the ExposureTime tag for presence only.'''

    description = 'ExposureTime MUST be present, or if this is a warning, may optionally be present'
    tag = pydicom.tag.Tag((0x0018, 0x1150))
    regex = re.compile(r'.+')


class XRayTubeCurrentValidator(RegexValidator):
    '''A validator that checks the XRayTubeCurrent tag for presence only.'''

    description = 'XRayTubeCurrent MUST be present, or if this is a warning, may optionally be present'
    tag = pydicom.tag.Tag((0x0018, 0x1151))
    regex = re.compile(r'.+')


class ExposureValidator(RegexValidator):
    '''A validator that checks the Exposure tag for presence only.'''

    description = 'Exposure MUST be present, or if this is a warning, may optionally be present'
    tag = pydicom.tag.Tag((0x0018, 0x1152))
    regex = re.compile(r'.+')


class CTDIvolValidator(RegexValidator):
    '''A validator that checks the CTDIvol tag for presence only.'''

    description = 'CTDIvol MUST be present, or if this is a warning, may optionally be present'
    tag = pydicom.tag.Tag((0x0018, 0x9345))
    regex = re.compile(r'.+')


class CTDIPhantomTypeCodeSequenceValidator(RegexValidator):
    '''A validator that checks the CTDIPhantomTypeCodeSequence tag for presence only.'''

    description = 'CTDIPhantomTypeCodeSequence MUST be present, or if this is a warning, may optionally be present'
    tag = pydicom.tag.Tag((0x0018, 0x9346))
    regex = re.compile(r'.+')


class RescaleInterceptValidator(RegexValidator):
    '''A validator that checks the RescaleIntercept tag for presence only.'''

    description = 'RescaleIntercept MUST be present, or if this is a warning, may optionally be present'
    tag = pydicom.tag.Tag((0x0028, 0x1052))
    regex = re.compile(r'.+')


class RescaleSlopeValidator(RegexValidator):
    '''A validator that checks the RescaleSlope tag for presence only.'''

    description = 'RescaleSlope must be present, or if this is a warning, may optionally be present'
    tag = pydicom.tag.Tag((0x0028, 0x1053))
    regex = re.compile(r'.+')
