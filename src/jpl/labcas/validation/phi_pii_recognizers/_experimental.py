# encoding: utf-8

'''🛂 EDRN DICOM Validation: experimental PHI/PII recognizers.'''

from .._classes import PHI_PII_Recognizer, HeaderFinding, Finding
import pydicom, logging

_logger = logging.getLogger(__name__)


class Accepting_PHI_PII_Recognizer(PHI_PII_Recognizer):
    '''A PHI/PII recognizer that never finds any PHI or PII in a DICOM dataset.'''
    
    description = 'Always accepts: never finds any PHI or PII in a DICOM dataset, for testing purposes'
    
    def recognize(self, ds: pydicom.Dataset) -> list[Finding]:
        _logger.debug('👍 Accepting recognizer giving no findings for %s for testing purposes', ds.filename)
        return []


class Rejecting_PHI_PII_Recognizer(PHI_PII_Recognizer):
    '''A PHI/PII recognizer that always finds PHI or PII in a DICOM dataset.'''

    description = 'Always rejects: finds PHI or PII in a DICOM dataset no matter what, for testing purposes'

    def recognize(self, ds: pydicom.Dataset) -> list[Finding]:
        _logger.debug('👎 Rejecting recognizer "finding" PHI/PII in %s for testing purposes', ds.filename)
        return [
            HeaderFinding(
                file=ds.filename,
                value='Jane Doe', score=1.0, tag=pydicom.tag.Tag((0x0008, 0x0005)),
                description='PHI/PII artificially found for testing purposes, name of patient'
            )
        ]
