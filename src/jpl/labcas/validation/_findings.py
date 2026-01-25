# encoding: utf-8

'''🛂 EDRN DICOM Validation: findings.'''

from __future__ import annotations
from functools import lru_cache
from dataclasses import dataclass
from typing import ClassVar, Optional
from abc import ABC, abstractmethod
from collections import defaultdict
import pydicom, argparse, logging, re, csv, os.path, sqlite3
from pydicom.tag import Tag
from pydicom import datadict
from ._files import PotentialFile

_logger = logging.getLogger(__name__)


@dataclass
class Finding:
    '''A finding in a DICOM file.'''
    file: PotentialFile           # The potential file that contains the finding
    value: str                    # Text value of the finding
    score: float = 1.0            # Severity, where 0.0 is nothing and 1.0 is completely severe

    @abstractmethod
    def kind(self) -> str:
        '''Return the kind of this finding.'''
        raise NotImplementedError(f'{self.__class__.__name__} must implement the «kind» method')

    @abstractmethod
    def report(self) -> list[str]:
        '''Report on this finding to the `where` destination.'''
        raise NotImplementedError(f'{self.__class__.__name__} must implement the «report» method')
    
    @abstractmethod
    def generate_database_fields(self) -> tuple[str, str | None, str | None, int | None, Tag | None]:
        '''Generate database fields for this finding.
        
        Returns:
            Tuple of (finding_type, description, pattern, index, tag_obj)
        '''
        raise NotImplementedError(f'{self.__class__.__name__} must implement the «generate_database_fields» method')
    
    def organization_parts(self) -> tuple[str, str, str]:
        '''Return the blinded site ID, event ID, and file name of this finding as a tuple of 3 strings.
        '''
        return self.file.site_id, self.file.event_id, self.file.path

    def __hash__(self) -> int:
        '''Return a hash of the finding.'''
        return hash((self.file.path, self.value, self.score))

    def __eq__(self, other: Finding) -> bool:
        '''Return True if the two findings are equal.'''
        return self.file.path == other.file.path and self.value == other.value

    def __lt__(self, other: Finding) -> bool:
        '''Return True if the current finding is less than the other finding.'''
        return self.file.path < other.file.path or (self.file.path == other.file.path and self.value < other.value and self.score < other.score)


@dataclass
class ErrorFinding(Finding):
    '''A finding in a DICOM file that is an error.'''
    error_message: str | None = None

    def kind(self) -> str:
        return '❌ Error'

    def report(self) -> list[str]:
        return [self.value, self.error_message]
    
    def generate_database_fields(self) -> tuple[str, str | None, str | None, int | None, Tag | None]:
        '''Generate database fields for this error finding.'''
        return (self.__class__.__name__, self.error_message, None, None, None)
    
    def __hash__(self) -> int:
        '''Return a hash of the error finding.'''
        return super().__hash__() ^ hash(self.error_message)

    def __eq__(self, other: ErrorFinding) -> bool:
        '''Return True if the two error findings are equal.'''
        return super().__eq__(other) and self.error_message == other.error_message

    def __lt__(self, other: ErrorFinding) -> bool:
        '''Return True if the current error finding is less than the other error finding.'''
        return super().__lt__(other) or (super().__eq__(other) and self.error_message < other.error_message)


@dataclass
class ValidationFinding(Finding):
    '''A finding in a DICOM file that is a validation problem.'''

    tag: Tag | None = None
    description: str | None = None

    def kind(self) -> str:
        return '⚠️ Missing Required Tags'

    def report(self) -> list[str]:
        if self.description:
            detail = f'Failed core tag validation: {self.description} — please review for completeness and format'
        else:
            detail = 'Failed core tag validation — please review for completeness and format'
        tag_name = datadict.keyword_for_tag(self.tag) if self.tag else 'unknown tag'
        return [f'{self.tag} ({tag_name})', f'«{self.value}»', detail]

    def generate_database_fields(self) -> tuple[str, str | None, str | None, int | None, Tag | None]:
        '''Generate database fields for this validation finding.'''
        return (self.__class__.__name__, self.description, None, None, self.tag)

    def __hash__(self) -> int:
        '''Return a hash of the validation finding.'''
        return super().__hash__() ^ hash(self.tag) ^ hash(self.description)

    def __eq__(self, other: ValidationFinding) -> bool:
        '''Return True if the two validation findings are equal.'''
        return super().__eq__(other) and self.tag == other.tag and self.description == other.description

    def __lt__(self, other: ValidationFinding) -> bool: 
        '''Return True if the current validation finding is less than the other validation finding.'''
        return super().__lt__(other) or (super().__eq__(other) and self.tag < other.tag and self.description < other.description)


@dataclass
class WarningFinding(Finding):
    '''A finding in a DICOM file that is a warning.'''

    tag: Tag | None = None
    description: str | None = None

    def kind(self) -> str:
        return '👮 Warning'
    
    def report(self) -> list[str]:
        if self.description:
            detail = f'Warning: {self.description}'
        else:
            detail = 'Warning for not a more specific reason'
        tag_name = datadict.keyword_for_tag(self.tag) if self.tag else 'unknown tag'
        return [f'{self.tag} ({tag_name})', f'«{self.value}»', detail]    

    def generate_database_fields(self) -> tuple[str, str | None, str | None, int | None, Tag | None]:
        '''Generate database fields for this warning finding.'''
        return (self.__class__.__name__, self.description, None, None, self.tag)
    
    def __hash__(self) -> int:
        '''Return a hash of the warning finding.'''
        return super().__hash__() ^ hash(self.description)
    
    def __eq__(self, other: WarningFinding) -> bool:
        '''Return True if the two warning findings are equal.'''
        return super().__eq__(other) and self.tag == other.tag and self.description == other.description

    def __lt__(self, other: WarningFinding) -> bool:
        '''Return True if the current warning finding is less than the other warning finding.'''
        return super().__lt__(other) or (super().__eq__(other) and self.tag < other.tag and self.description < other.description)


@dataclass
class PHI_PII_Finding(Finding):
    '''A finding in a DICOM file that is PHI or PII.'''
    
    def __hash__(self) -> int:
        '''Return a hash of the PHI/PII finding.'''
        return super().__hash__()


@dataclass
class HeaderFinding(PHI_PII_Finding):
    '''A finding in a DICOM header.'''
    tag: Tag | None = None
    description: str | None = None

    def kind(self) -> str:
        return '🙈 Possible PHI/PII in Header'

    def report(self) -> list[str]:
        if self.description:
            detail = f'Possible PHI/PII detection (score {self.score:.2f}): {self.description}'
        else:
            detail = f'Possible PHI/PII detection (score {self.score:.2f})'
        if self.tag:
            tag_str = f'{self.tag} ({datadict.keyword_for_tag(self.tag)})'
        else:
            tag_str = 'unknown tag'
        return [tag_str, f'«{self.value}»', detail]

    def generate_database_fields(self) -> tuple[str, str | None, str | None, int | None, Tag | None]:
        '''Generate database fields for this header finding.'''
        return (self.__class__.__name__, self.description, None, None, self.tag)

    def __hash__(self) -> int:
        '''Return a hash of the header finding.'''
        return super().__hash__() ^ hash(self.tag) ^ hash(self.description)

    def __eq__(self, other: HeaderFinding) -> bool:
        '''Return True if the two header findings are equal.'''
        return super().__eq__(other) and self.tag == other.tag and self.description == other.description

    def __lt__(self, other: HeaderFinding) -> bool:
        '''Return True if the current header finding is less than the other header finding.'''
        return super().__lt__(other) or (super().__eq__(other) and self.tag < other.tag and self.description < other.description)


@dataclass
class ImageFinding(PHI_PII_Finding):
    '''A finding in a DICOM image.'''
    pattern: str = 'unknown'
    index: int = -1

    def kind(self) -> str:
        return '🖼️ Possible Burned-in PHI/PII (Pixels)'

    def report(self) -> list[str]:
        # 🔮 Figure out how to describe OCR PHI/PII
        return [self.value, f'Detected with pattern {self.pattern} at frame index {self.index}']

    def generate_database_fields(self) -> tuple[str, str | None, str | None, int | None, Tag | None]:
        '''Generate database fields for this image finding.'''
        return (self.__class__.__name__, None, self.pattern, self.index, None)

    def __hash__(self) -> int:
        '''Return a hash of the image finding.'''
        return super().__hash__() ^ hash(self.pattern) ^ hash(self.index)

    def __eq__(self, other: ImageFinding) -> bool:
        '''Return True if the two image findings are equal.'''
        return super().__eq__(other) and self.pattern == other.pattern and self.index == other.index

    def __lt__(self, other: ImageFinding) -> bool:  
        '''Return True if the current image finding is less than the other image finding.'''
        return super().__lt__(other) or (super().__eq__(other) and self.pattern < other.pattern and self.index < other.index)
