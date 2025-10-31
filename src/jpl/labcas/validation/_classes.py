# encoding: utf-8

'''🛂 EDRN DICOM Validation: classes.'''

from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
from abc import ABC, abstractmethod
from collections import defaultdict
import pydicom, argparse, logging, re, csv
from pydicom.tag import Tag
from pydicom import datadict

_logger = logging.getLogger(__name__)


@dataclass
class Finding:
    '''A finding in a DICOM file.'''
    file: str           # Relative path of the file containing the finding
    value: str          # Text value of the finding
    score: float = 1.0  # Severity, where 0.0 is nothing and 1.0 is completely severe

    # Regular expression for parsing organization parts from file paths
    _organization_re = re.compile(r'([^/]+)/(\d{7})/(.+)$')

    @abstractmethod
    def kind(self) -> str:
        '''Return the kind of this finding.'''
        raise NotImplementedError(f'{self.__class__.__name__} must implement the «kind» method')

    @abstractmethod
    def report(self) -> list[str]:
        '''Report on this finding to the `where` destination.'''
        raise NotImplementedError(f'{self.__class__.__name__} must implement the «report» method')
    
    def organization_parts(self) -> tuple[str, str, str]:
        '''Return the blinded site ID, event ID, and file name of this finding as a tuple of 3 strings.
        '''
        match = self._organization_re.search(self.file)
        if match:
            return match.groups()
        else:
            # Fallback if no match found
            return ('«unknown site»', '«unknown event»', self.file.split('/')[-1] if '/' in self.file else self.file)


@dataclass
class ErrorFinding(Finding):
    '''A finding in a DICOM file that is an error.'''
    error_message: str | None = None

    def kind(self) -> str:
        return '❌ Error'

    def report(self) -> list[str]:
        return [self.value, self.error_message]


@dataclass
class ValidationFinding(Finding):
    '''A finding in a DICOM file that is a validation problem.'''

    tag: Tag | None = None
    description: str | None = None

    def kind(self) -> str:
        return '⚠️ Validation'

    def report(self) -> list[str]:
        if self.description:
            detail = f'Failed core tag validation: {self.description} — please review for completeness and format'
        else:
            detail = 'Failed core tag validation — please review for completeness and format'
        tag_name = datadict.keyword_for_tag(self.tag) if self.tag else 'unknown tag'
        return [f'{self.tag} ({tag_name})', f'«{self.value}»', detail]


@dataclass
class PHI_PII_Finding(Finding):
    '''A finding in a DICOM file that is PHI or PII.'''


@dataclass
class HeaderFinding(PHI_PII_Finding):
    '''A finding in a DICOM header.'''
    tag: Tag | None = None
    description: str | None = None

    def kind(self) -> str:
        return '🙈 Header'

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


@dataclass
class ImageFinding(PHI_PII_Finding):
    '''A finding in a DICOM image.'''
    pattern: str = 'unknown'
    index: int = -1

    def kind(self) -> str:
        return '🖼️ Pixels'

    def report(self) -> list[str]:
        # 🔮 Figure out how to describe OCR PHI/PII
        return [self.value, f'Detected with pattern {self.pattern} at frame index {self.index}']


class PHI_PII_Recognizer(ABC):
    '''Base class for PHI/PII recognizers.'''

    description: ClassVar[str]

    def __init__(self, args: argparse.Namespace):
        '''Initialize the recognizer with the given arguments.

        Subclasses may use the args in arbitrary ways or ignore them entirely.
        '''
        pass

    def __init_subclass__(cls, **kwargs):
        '''Initialize the subclass.'''
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, 'description'):
            raise TypeError(f'{cls.__name__} must define a «description» class attribute')

    @abstractmethod
    def recognize(self, ds: pydicom.Dataset) -> list[Finding]:
        '''Recognize PHI/PII in the given DICOM dataset and return a list of findings.'''
        raise NotImplementedError(f'{self.__class__.__name__} must implement the «recognize» method')


class Validator(ABC):
    '''Base class for validators.'''

    description: ClassVar[str]
    tag: ClassVar[Tag]

    def __init_subclass__(cls, **kwargs):
        '''Initialize the subclass.'''
        super().__init_subclass__(**kwargs)
        # Skip checking specific intermediate abstract classes like RegexValidator
        # These classes have their own __init_subclass__ that will enforce requirements
        if cls.__name__ in ('RegexValidator', 'DICOMUIDValidator'):
            return
        
        # Only enforce attribute requirements for concrete classes (not abstract intermediate classes)
        # Check if this class is abstract by looking for @abstractmethod decorators in the class
        import inspect
        abstract_methods = [
            name for name, method in inspect.getmembers(cls, predicate=inspect.isfunction)
            if getattr(method, '__isabstractmethod__', False)
        ]
        if abstract_methods:  # If class has abstract methods, skip the requirement check
            return
        # Otherwise enforce the requirement
        for attr in ('description', 'tag'):
            if not hasattr(cls, attr):
                raise TypeError(f'{cls.__name__} must define a «{attr}» class attribute')

    @abstractmethod
    def validate(self, ds: pydicom.Dataset) -> list[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        raise NotImplementedError(f'{self.__class__.__name__} must implement the «validate» method')


class Report:
    '''A report of findings.
    
    Future polymorphism: subclasses could make different reports, e.g. HTML, JSON, etc.
    '''
    def __init__(self, findings: list[Finding], output_file: str, score: float):
        '''Initialize the report with the given findings.
        
        Don't report findings unless they are equal to or exceed the score.
        '''
        self.findings, self.output_file, self.score = findings or [], output_file, score

    def _organize_report(self) -> dict:
        '''Organize the report into a dictionary.
    
        The dictionary is organized by blinded site ID as a keys and values of dictionaries of event IDs
        as keys and values of dictionaries of file names as keys and findings as values.
        '''
        report: defaultdict[str, defaultdict[str, defaultdict[str, list[Finding]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for finding in self.findings:
            site_id, event_id, file_name = finding.organization_parts()
            report[site_id][event_id][file_name].append(finding)
        return report

    def generate_report_csv(self):
        '''Generate a CSV report of the findings and write it to the `output_file`.
        
        This is currently not used.
        '''
        _logger.info('📝 Generating report to %s', self.output_file)
        with open(self.output_file, 'w', newline='') as io:
            writer = csv.writer(io)
            writer.writerow(['Site ID', 'Event ID', 'File Name', 'Type', 'Details'])
            for site_id, event_ids in self._organize_report().items():
                for event_id, file_names in event_ids.items():
                    for file_name, findings in file_names.items():
                        for finding in findings:
                            row = [site_id, event_id, file_name] + finding.report()
                            writer.writerow(row)

    def generate_report(self):
        '''Generate a Markdown-format report of the findings and write it to the `output_file`.'''

        _logger.info('📝 Generating report to %s', self.output_file)
        with open(self.output_file, 'w') as io:
            io.write('# 🧑‍💼 EDRN DICOM Validation Report\n\n')
            io.write('This report is generated by the EDRN DICOM Validation tool.\n')
            io.write("It's organized by sites, then by event IDs, then by files and the findings in those files.\n\n")
            threshold_findings = [f for f in self.findings if f.score >= self.score]
            io.write(f'There are {len(self.findings)} findings, but of those {len(threshold_findings)} are above the threshold of {self.score:.2f}.\n\n')

            for site_id, event_ids in self._organize_report().items():
                io.write(f'## 🏥 Site ID: `{site_id}`\n\n')
                io.write(f'Events in this site: {len(event_ids)}.\n\n')

                for event_id, file_names in event_ids.items():
                    io.write(f'### 🗓️ Event ID: `{event_id}`\n\n')
                    io.write(f'Files in this event: {len(file_names)}.\n\n')

                    displayed_one_file = False
                    for file_name, findings in file_names.items():
                        have_scored_findings = any(f.score >= self.score for f in findings)                        
                        if have_scored_findings:
                            io.write(f'\n#### 📄 File Name: `{file_name}`\n\n')
                            displayed_one_file = True
                            kinds = sorted(list(set([f.kind() for f in findings])))
                            io.write('| Score | Kind | Details |\n')
                            io.write('|------:|:----:|:--------|\n')
                            for kind in kinds:
                                scored_findings = sorted(
                                    [f for f in findings if f.score >= self.score and f.kind() == kind],
                                    key=lambda x: x.score, reverse=True
                                )
                                if len(scored_findings) > 0:
                                    for finding in scored_findings:
                                        score, details = finding.score, ", ".join(finding.report())
                                        io.write(f'| {score:.2f} | {kind} | {details} |\n')
                                else:
                                    io.write(f'| | {kind} | No findings found at or above the threshold of {self.score:.2f} for {kind} |\n')
                    if not displayed_one_file:
                        io.write(f'No findings for any file at or above the threshold of {self.score:.2f} in this event.\n')
                    io.write('\n')
                io.write('\n')
