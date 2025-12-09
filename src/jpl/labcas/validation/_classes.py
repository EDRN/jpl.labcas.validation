# encoding: utf-8

'''🛂 EDRN DICOM Validation: classes.'''

from __future__ import annotations
from functools import lru_cache
from dataclasses import dataclass
from typing import ClassVar, Optional
from abc import ABC, abstractmethod
from collections import defaultdict
import pydicom, argparse, logging, re, csv, os.path, sqlite3
from pydicom.tag import Tag
from pydicom import datadict

_logger = logging.getLogger(__name__)

@dataclass
class PotentialFile:
    '''A file that we will scan for PHI/PII and check for compliance with EDRN validation requirements.'''
    path: str           # Relative path of the file
    site_id: str        # Blinded site ID
    event_id: str       # Event ID
    file_name: str      # File name

    # Regex for parsing organization parts from file paths
    _organization_re = re.compile(r'([^/]+)/(\d{7})/(.+)$')  # blah/blah/Images_site_XYX/1234567/f1/f2/…/file.dcm

    def __init__(self, path: str, site_id: str = None, event_id: str = None):
        '''Initialize the potential file with the given file path and optional site and event IDs.'''
        self.path = path

        search_result = self._organization_re.search(path)
        if search_result:
            self.site_id, self.event_id, self.file_name = search_result.groups()
        else:
            self.site_id, self.event_id, self.file_name = '«unknown site»', '«unknown event»', os.path.basename(path)

        if site_id: self.site_id = site_id
        if event_id: self.event_id = event_id

    @lru_cache
    def _read_dicom_file(self, stop_before_pixels: bool = False, force: bool = False) -> pydicom.Dataset:
        '''Read the DICOM file and return a dataset.'''
        return pydicom.dcmread(self.path, stop_before_pixels=stop_before_pixels, force=force)

    def dcmread(self, stop_before_pixels: bool = False, force: bool = False, cache: bool = True) -> pydicom.Dataset:
        '''Read the DICOM file and return a dataset.'''

        if cache:
            return self._read_dicom_file(stop_before_pixels, force)
        else:
            return pydicom.dcmread(self.path, stop_before_pixels=stop_before_pixels, force=force)

    def __repr__(self) -> str:
        '''Return a convenient representation of the potential file.'''
        return (
            f'{self.__class__.__name__}(path={self.path}, site_id={self.site_id}, event_id={self.event_id}, '
            f'file_name={self.file_name})'
        )

    def __str__(self) -> str:
        '''Return a string representation of the potential file.'''
        return self.path

    def __hash__(self) -> int:
        '''Return a hash of the potential file.'''
        return hash(self.path)

    def __eq__(self, other: PotentialFile) -> bool:
        '''Return True if the two potential files are equal.'''
        return self.path == other.path

    def __lt__(self, other: PotentialFile) -> bool:
        '''Return True if the current potential file is less than the other potential file.'''
        return self.path < other.path
        

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
    def recognize(self, potential_file: PotentialFile) -> list[Finding]:
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
    def validate(self, potential_file: PotentialFile) -> list[ValidationFinding]:
        '''Validate the given DICOM dataset and return a list of findings.'''
        raise NotImplementedError(f'{self.__class__.__name__} must implement the «validate» method')


class Report:
    '''A report of findings.
    
    Future polymorphism: subclasses could make different reports, e.g. HTML, JSON, etc.
    
    Can work with either a list of findings (for backward compatibility) or a SQLite database path
    (for memory-efficient processing).
    '''
    def __init__(self, findings: Optional[list[Finding]] = None, score: float = 1.0, db_path: Optional[str] = None):
        '''Initialize the report with the given findings or database path.
        
        Don't report findings unless they are equal to or exceed the score.
        
        Args:
            findings: Optional list of Finding objects (for backward compatibility)
            score: Minimum score threshold for reporting findings
            db_path: Optional path to SQLite database containing findings (preferred for memory efficiency)
        '''
        if db_path and findings:
            raise ValueError('Cannot specify both findings list and database path')
        if not db_path and not findings:
            raise ValueError('Must specify either findings list or database path')
        
        self.findings = findings
        self.db_path = db_path
        self.score = score

    def _get_finding_kind(self, finding_type: str) -> str:
        '''Get the kind string for a finding type.'''
        kind_map = {
            'ErrorFinding': '❌ Error',
            'ValidationFinding': '⚠️ Missing Required Tags',
            'HeaderFinding': '🙈 Possible PHI/PII in Header',
            'ImageFinding': '🖼️ Possible Burned-in PHI/PII (Pixels)',
        }
        return kind_map.get(finding_type, '❓ Unknown')

    def _format_finding_report(self, finding_type: str, value: str, score: float, tag: Optional[str], 
                                description: Optional[str], pattern: Optional[str], index_val: Optional[int]) -> list[str]:
        '''Format finding report as a list of strings (matching the report() method format).'''
        from pydicom import datadict
        
        if finding_type == 'ErrorFinding':
            return [value, description or '']
        elif finding_type == 'ValidationFinding':
            if description:
                detail = f'Failed core tag validation: {description} — please review for completeness and format'
            else:
                detail = 'Failed core tag validation — please review for completeness and format'
            tag_str = self._format_finding_tag(finding_type, tag)
            return [tag_str, f'«{value}»', detail]
        elif finding_type == 'HeaderFinding':
            if description:
                detail = f'Possible PHI/PII detection (score {score:.2f}): {description}'
            else:
                detail = f'Possible PHI/PII detection (score {score:.2f})'
            tag_str = self._format_finding_tag(finding_type, tag)
            return [tag_str, f'«{value}»', detail]
        elif finding_type == 'ImageFinding':
            return [value, f'Detected with pattern {pattern or "unknown"} at frame index {index_val or -1}']
        else:
            return [value]

    def _format_finding_tag(self, finding_type: str, tag: Optional[str]) -> str:
        '''Format tag information for CSV output.'''
        from pydicom import datadict
        
        if finding_type in ('ValidationFinding', 'HeaderFinding') and tag:
            try:
                parts = tag.split(',')
                if len(parts) == 2:
                    group = int(parts[0])
                    element = int(parts[1])
                    tag_obj = Tag((group, element))
                    tag_name = datadict.keyword_for_tag(tag_obj)
                    return f'{tag_obj} ({tag_name})'
            except:
                pass
        return 'unknown tag'

    def generate_csv_report(self):
        '''Generate CSV files of the findings.
        
        If db_path is set, queries the database directly without loading all findings into memory.
        Otherwise, uses the findings list.
        '''
        _logger.info('📝 Generating CSV reports')
        _header = ['Site ID', 'Event ID', 'File Name', 'Score', 'Findings', 'Details']

        if self.db_path:
            # Query database directly for memory efficiency
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            try:
                # Get all unique site_ids
                cursor = conn.execute('''
                    SELECT DISTINCT site_id 
                    FROM findings 
                    WHERE score >= ?
                    ORDER BY site_id
                ''', (self.score,))
                
                site_ids = [row[0] for row in cursor.fetchall()]
                
                for site_id in site_ids:
                    # Get all findings for this site (all events), grouped by file
                    cursor = conn.execute('''
                        SELECT event_id, file_path, file_name, finding_type, value, score, tag, description, pattern, index_val
                        FROM findings
                        WHERE site_id = ? AND score >= ?
                        ORDER BY event_id, file_path, finding_type, score DESC
                    ''', (site_id, self.score))
                    
                    # Group by event_id, file_path, and finding_type
                    event_file_findings: defaultdict[str, defaultdict[str, defaultdict[str, list]]] = defaultdict(
                        lambda: defaultdict(lambda: defaultdict(list))
                    )
                    for row in cursor:
                        event_id, file_path, file_name, finding_type, value, score, tag, description, pattern, index_val = row
                        event_file_findings[event_id][file_path][finding_type].append({
                            'value': value,
                            'score': score,
                            'tag': tag,
                            'description': description,
                            'pattern': pattern,
                            'index_val': index_val
                        })
                    
                    # Process each event for this site
                    for event_id in sorted(event_file_findings.keys()):
                        # Write CSV file for this site_id-event_id combination
                        with open(f'{site_id}-{event_id}.csv', 'w', newline='') as io:
                            writer = csv.writer(io)
                            writer.writerow(_header)
                            
                            file_findings = event_file_findings[event_id]
                            for file_path, finding_types in sorted(file_findings.items()):
                                file_name = os.path.basename(file_path)
                                kinds = sorted(finding_types.keys())
                                
                                for kind_type in kinds:
                                    kind = self._get_finding_kind(kind_type)
                                    findings_list = finding_types[kind_type]
                                    
                                    # Sort by score descending
                                    findings_list.sort(key=lambda x: x['score'], reverse=True)
                                    
                                    for finding_data in findings_list:
                                        report_parts = self._format_finding_report(
                                            kind_type, finding_data['value'], finding_data['score'],
                                            finding_data['tag'], finding_data['description'],
                                            finding_data['pattern'], finding_data['index_val']
                                        )
                                        details = ", ".join(report_parts)
                                        
                                        writer.writerow([
                                            site_id, 
                                            event_id, 
                                            file_name, 
                                            finding_data['score'], 
                                            kind,
                                            details
                                        ])
            finally:
                conn.close()
        else:
            # Use in-memory findings list (backward compatibility)
            organized = self._organize_report()
            for site_id, event_ids in organized.items():
                # Process all events for this site
                for event_id in sorted(event_ids.keys()):
                    # Write CSV file for this site_id-event_id combination
                    with open(f'{site_id}-{event_id}.csv', 'w', newline='') as io:
                        writer = csv.writer(io)
                        writer.writerow(_header)
                        file_names = event_ids[event_id]
                        for file_name, findings in sorted(file_names.items()):
                            kinds = sorted(list(set([f.kind() for f in findings])))
                            for kind in kinds:
                                scored_findings = sorted(
                                    [f for f in findings if f.score >= self.score and f.kind() == kind],
                                    key=lambda x: x.score, reverse=True
                                )
                                if len(scored_findings) > 0:
                                    for finding in scored_findings:
                                        score, details = finding.score, ", ".join(finding.report())
                                        writer.writerow([site_id, event_id, file_name, score, kind, details])

    def _organize_report(self) -> dict:
        '''Organize the report into a dictionary (used only when findings list is provided).
    
        The dictionary is organized by blinded site ID as a keys and values of dictionaries of event IDs
        as keys and values of dictionaries of file names as keys and findings as values.
        '''
        if not self.findings:
            raise ValueError('_organize_report() can only be used when findings list is provided')
        
        report: defaultdict[str, defaultdict[str, defaultdict[str, list[Finding]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for finding in self.findings:
            site_id, event_id, file_name = finding.organization_parts()
            report[site_id][event_id][file_name].append(finding)
        return report

    def generate_report(self):
        return self.generate_csv_report()
