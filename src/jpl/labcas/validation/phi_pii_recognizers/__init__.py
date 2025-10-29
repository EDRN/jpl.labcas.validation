# encoding: utf-8

'''🛂 EDRN DICOM Validation: PHI/PII recognizers.'''

from ._experimental import Accepting_PHI_PII_Recognizer, Rejecting_PHI_PII_Recognizer
from ._simple_scoring import SimpleScoring_PHI_PII_Recognizer

PHI_PII_RECOGNIZERS = {
    'accepting': Accepting_PHI_PII_Recognizer,
    'rejecting': Rejecting_PHI_PII_Recognizer,
    'simple-scoring': SimpleScoring_PHI_PII_Recognizer,
}

DEFAULT_PHI_PII_RECOGNIZER = 'simple-scoring'

__all__ = [PHI_PII_RECOGNIZERS, DEFAULT_PHI_PII_RECOGNIZER]
