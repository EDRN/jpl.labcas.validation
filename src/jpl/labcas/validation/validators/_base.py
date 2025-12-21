# encoding: utf-8

'''🛂 EDRN DICOM Validation: base validator classes.'''

from .._classes import Validator, ValidationFinding, PotentialFile, WarningFinding
from .._functions import textify_dicom_value
from pydicom.dataelem import convert_raw_data_element
import re, pydicom, logging
from pydicom import datadict
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
        if cls.__name__ in ('DICOMUIDValidator', 'YMDValidator', 'CaseInsensitiveAndWarningRegexValidator'):
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

    def _match_pattern(self, value: str):
        '''Match the given value against our regex pattern.'''
        return self.regex.match(value)

    def validate(self, potential_file: PotentialFile) -> list[ValidationFinding]:
        '''Validate the given DICOM dataset `potential_file` against our regex pattern and return the findings.'''
        ds = potential_file.dcmread(stop_before_pixels=True, force=False)
        findings: list[ValidationFinding] = []
        elem = ds.get_item(self.tag)
        if elem is None:
            findings.append(ValidationFinding(
                file=potential_file, value='tag missing', tag=self.tag,
                description=f'Required tag not found in DICOM dataset'
            ))
        else:
            try:
                elem = convert_raw_data_element(elem) 
            except AttributeError as ex:
                # Use elem directly as it is already a DataElement
                pass
            value = textify_dicom_value(elem.value)
            if not value or not any(v.strip() for v in value):
                findings.append(ValidationFinding(
                    file=potential_file, value='value missing', tag=self.tag,
                    description=f'Tag found but missing a value in DICOM dataset'
                ))
            else:
                for v in value:
                    v = v.strip()
                    if not v: continue
                    _logger.debug(
                        '🫆 Class %s checking value «%s» for tag %s in %s',
                        self.__class__.__name__, v, self.tag, potential_file
                    )
                    if not self._match_pattern(v):
                        findings.append(ValidationFinding(
                            file=potential_file, value=v, tag=self.tag,
                            description=f'Value for tag does not match expected pattern: {self.description}'
                        ))
        return findings
    

class DICOMUIDValidator(RegexValidator):
    '''An abstract validator that checks for a DICOM UID.'''

    regex = re.compile(r'^(?=.{1,64}$)[0-9]+\.[0-9]+(\.[0-9]+)*$')


class YMDValidator(RegexValidator):
    '''An abstract validator that checks for a YYYYMMDD date.'''

    regex = re.compile(r'^[0-9]{8}$')


class CaseInsensitiveAndWarningRegexValidator(RegexValidator):
    '''An abstract validator that checks for a regex pattern and issue warnings.'''

    class _CaseMismatchError(Exception):
        '''Indicate that while the value might match the regex, it's doesn't match the letter case.'''
        pass

    def _match_pattern(self, value: str):
        '''Match the given value against our regex pattern.

        If the match fails, try again without regard to case. If that works, then raise an exception.
        '''
        matches = self.regex.match(value)
        if matches is not None: return matches
        case_insensitive_regex = re.compile(self.regex.pattern, self.regex.flags | re.IGNORECASE)
        matches = case_insensitive_regex.match(value)
        if matches is not None: raise self._CaseMismatchError(value)

    def validate(self, potential_file: PotentialFile) -> list[ValidationFinding]:
        try:
            return super().validate(potential_file)
        except self._CaseMismatchError as ex:
            tag_name = datadict.keyword_for_tag(self.tag) if self.tag else 'unknown tag'
            return [WarningFinding(
                file=potential_file, value=f'«{ex.args[0]}»', tag=self.tag,
                description=f'{self.tag} Value for {tag_name} matches expected pattern but uses incorrect case; {self.description}'
            )]
