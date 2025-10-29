# encoding: utf-8

'''🛂 EDRN DICOM Validation: errors.'''


class DirectoryError(Exception):
    '''A directory error.'''
    pass


class ValidationError(Exception):
    '''A validation error.'''
    pass


class PHI_PII_DetectionError(ValidationError):
    '''A PHI/PII detection error.'''
    pass


class ComplianceError(ValidationError):
    '''A compliance error.'''
    pass
