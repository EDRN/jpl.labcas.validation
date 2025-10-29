# encoding: utf-8

'''🛂 EDRN DICOM Validation: base validator classes.'''

from .._classes import Validator, ValidationFinding
from .._functions import textify_dicom_value
import re, pydicom, logging
from typing import ClassVar

_logger = logging.getLogger(__name__)


class RegexValidator(Validator):
    '''An abstract base class for validators that check a regex pattern against a value.
    
    Subclasses must define the «description», «tag», and «regex» class attributes.
    '''

    regex: ClassVar[re.Pattern]  # Subclasses must override with a concrete value
    
    def __init_subclass__(cls, **kwargs):
        '''Override to enforce our own requirements without calling parent check.'''
        # Don't call super().__init_subclass__() - we'll enforce our own requirements
        # We require description, tag, AND regex for concrete subclasses
        if cls.__name__ in ('DICOMUIDValidator', 'YMDValidator'):
            return

        import inspect
        # Check if this subclass is abstract (has abstract methods)
        abstract_methods = [
            name for name, method in inspect.getmembers(cls, predicate=inspect.isfunction)
            if getattr(method, '__isabstractmethod__', False)
        ]
        if not abstract_methods:  # Only check concrete classes
            for attr in ('description', 'tag', 'regex'):
                if not hasattr(cls, attr):
                    raise TypeError(f'{cls.__name__} must define a «{attr}» class attribute')

    def validate(self, ds: pydicom.Dataset) -> list[ValidationFinding]:
        '''Validate the given DICOM datasets `ds` against our regex pattern and return the findings.'''
        findings: list[ValidationFinding] = []
        elem = ds.get_item(self.tag)
        if elem is None:
            findings.append(ValidationFinding(
                file=ds.filename, value='tag missing', tag=self.tag,
                description=f'Required tag not found in DICOM dataset'
            ))
        else:
            value = textify_dicom_value(elem.value)
            if not value or not any(v.strip() for v in value):
                findings.append(ValidationFinding(
                    file=ds.filename, value='value missing', tag=self.tag,
                    description=f'Tag found but missing a value in DICOM dataset'
                ))
            else:
                for v in value:
                    v = v.strip()
                    if not v: continue
                    _logger.debug(
                        '🫆 Class %s checking value «%s» for tag %s in %s',
                        self.__class__.__name__, v, self.tag, ds.filename
                    )
                    if not self.regex.match(v):
                        findings.append(ValidationFinding(
                            file=ds.filename, value=v, tag=self.tag,
                            description=f'Value for tag does not match expected pattern: {self.description}'
                        ))
        return findings
    

class DICOMUIDValidator(RegexValidator):
    '''An abstract validator that checks for a DICOM UID.'''

    regex = re.compile(r'^(?=.{1,64}$)[0-9]+\.[0-9]+(\.[0-9]+)*$')


class YMDValidator(RegexValidator):
    '''An abstract validator that checks for a YYYYMMDD date.'''

    regex = re.compile(r'^[0-9]{8}$')
