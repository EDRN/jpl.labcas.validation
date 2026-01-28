# encoding: utf-8

'''🛂 EDRN DICOM Validation: classes.'''

from __future__ import annotations
from ._findings import Finding
from functools import lru_cache
from dataclasses import dataclass
from typing import ClassVar, Optional
from abc import ABC, abstractmethod
from collections import defaultdict
import pydicom, argparse, logging, re, csv, os.path, sqlite3
from pydicom.tag import Tag
from pydicom import datadict

_logger = logging.getLogger(__name__)


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
    def validate(self, potential_file: PotentialFile) -> set[ValidationFinding]:
        '''Validate the given DICOM dataset and return a set of findings.'''
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
        if db_path is None and findings is None:
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
            'WarningFinding': '👮 Warning',
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
        elif finding_type == 'WarningFinding':
            return [value, description or '']
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

    def generate_csv_report(self, output_directory: str):
        '''Generate CSV files of the findings.
        
        If db_path is set, queries the database directly without loading all findings into memory.
        Otherwise, uses the findings list.
        '''
        _logger.info('📝 Generating CSV reports')
        _header = ['Site ID', 'Event ID', 'File Name', 'Profile', 'Score', 'Findings', 'Details']

        if self.db_path:
            # Query database directly for memory efficiency
            _logger.info('Opening database at %s for reading', self.db_path)
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
                _logger.info('Found %d unique site IDs', len(site_ids))

                for site_id in site_ids:
                    _logger.info('Processing site ID %s', site_id)
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
                        output_file = os.path.join(output_directory, f'{site_id}-{event_id}.csv')
                        _logger.info('Processing event ID %s and opening file %s', event_id, output_file)
                        with open(output_file, 'w', newline='') as io:
                            writer = csv.writer(io)
                            writer.writerow(_header)
                            
                            file_findings = event_file_findings[event_id]
                            for file_path, finding_types in sorted(file_findings.items()):
                                file_name = os.path.basename(file_path)
                                # Get profile name for this file
                                from ._files import PotentialFile
                                potential_file = PotentialFile(file_path)
                                profile_name = potential_file.profile_name.value if potential_file.profile_name else 'Unknown'
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
                                            profile_name,
                                            finding_data['score'], 
                                            kind,
                                            details
                                        ])
            finally:
                _logger.info('Closing database connection')
                conn.close()
        else:
            # Use in-memory findings list (single-process mode)
            _logger.info('Using in-memory findings list')
            organized = self._organize_report()
            for site_id, event_ids in organized.items():
                # Process all events for this site
                for event_id in sorted(event_ids.keys()):
                    # Write CSV file for this site_id-event_id combination
                    output_file = os.path.join(output_directory, f'{site_id}-{event_id}.csv')
                    _logger.info('Processing event ID %s and opening file %s', event_id, output_file)
                    with open(output_file, 'w', newline='') as io:
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
                                    # Get profile name from the first finding (all findings for same file have same profile)
                                    profile_name = scored_findings[0].file.profile_name.value if scored_findings[0].file.profile_name else 'Unknown'
                                    for finding in scored_findings:
                                        score, details = finding.score, ", ".join(finding.report())
                                        writer.writerow([site_id, event_id, file_name, profile_name, score, kind, details])
        _logger.info('Finished generating CSV reports')

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

    def generate_report(self, output_directory: str):
        return self.generate_csv_report(output_directory)
