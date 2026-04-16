# encoding: utf-8

'''🛂 EDRN DICOM Validation.

Scans a folder of DICOM files and checks for PHI/PII (or as Heather likes to call it, "de-id", which
is clumsy as you're checking if de-identification happened by evidence of finding PHI or PII), and also
checks compliance with the EDRN core and MR requirements for DICOM tags.

To run this:

    validate-dicom-files \
        --url https://localhost:8984/solr/ \
        --output /labcas-data/labcas-backend/reports/edrn/COLLECTION \
        /labca-data/labcas-backend/archive/edrn/COLLECTION

The idea is to build a "filesystem database" of CSV files from each COLLECTION in `/labcas-data/labcas-backend/reports/edrn/COLLECTION`.

N.B.: This program generates enormous temporary files; you may wish to set `TMPDIR` to a directory on a spacious filesystem.

Later, you can then run:

    summarize-validation-reports /labcas-data/labcas-backend/reports/edrn

to get the summary.
'''

from ._argparse import add_standard_argparse_options
from ._classes import Report
from ._files import PotentialFile
from ._findings import Finding, ErrorFinding
from ._profiles import get_profile, ProfileName, PROFILES
from ._functions import check_directory, iterate_paths
from .const import PHI_PII_THRESHOLD, MINIMUM_FILE_SIZE, MINIMUM_MR_LOC_ROWS, MINIMUM_MR_LOC_COLUMNS
from .phi_pii_recognizers import PHI_PII_RECOGNIZERS, DEFAULT_PHI_PII_RECOGNIZER
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count, get_context
from typing import Iterable
import argparse, sys, logging, os, pydicom, pysolr, os.path, tempfile, sqlite3, threading, traceback, humanize


__doc__ = '🛂 EDRN DICOM Validation: check for PHI/PII and compliance with EDRN core and MR requirements for DICOM tags'
__copyright__ = 'Copyright © 2025–2026 California Institute of Technology'
__license__ = 'Apache 2.0'
_recognizer = None  # The one recognizer we'll need for all workers for all files
_logger = logging.getLogger(__name__)
_db_path = None  # Path to SQLite database for storing findings
_db_lock = None  # Lock for database access (thread lock in single-process; shared process lock in multi-process)


def _score_type(value: str) -> float:
    '''Validate that the score is between 0.0 and 1.0 (inclusive).'''
    try:
        score = float(value)
        if not (0.0 <= score <= 1.0):
            raise argparse.ArgumentTypeError(f'{value} is not in the range [0.0, 1.0]')
        return score
    except ValueError:
        raise argparse.ArgumentTypeError(f'{value} is not a valid floating point number')


def _init_worker(recognizer_name: str, recognizer_args: dict, db_path: str = None, db_write_lock=None):
    '''Initialize the worker by instantiating the global recognizer by name and its needed arguments.
    
    Args:
        recognizer_name: Name of the recognizer to use
        recognizer_args: Dictionary of arguments for the recognizer
        db_path: Optional path to SQLite database (None for single-process mode)
        db_write_lock: Optional shared lock for serializing DB writes across processes (required when db_path is set)
    '''
    global _recognizer, _db_path, _db_lock
    # Configure logging for this worker process to match the parent process
    logging.basicConfig(level=recognizer_args.get('loglevel', logging.INFO), format='%(levelname)s %(message)s')
    _recognizer = PHI_PII_RECOGNIZERS[recognizer_name](argparse.Namespace(**recognizer_args))
    _db_path = db_path
    _db_lock = db_write_lock if db_path else None  # Shared cross-process lock when using database


def _write_finding_to_db(conn: sqlite3.Connection, finding: Finding):
    '''Write a single finding to the database.'''
    # Get database fields from the finding object itself (polymorphic call)
    finding_type, description, pattern, index, tag_obj = finding.generate_database_fields()
    
    # Serialize tag as "group,element" string for storage
    tag_str = None
    if tag_obj:
        tag_str = f'{tag_obj.group},{tag_obj.element}'
    
    conn.execute('''
        INSERT INTO findings (file_path, site_id, event_id, file_name, finding_type, value, score, tag, description, pattern, index_val)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        finding.file.path,
        finding.file.site_id,
        finding.file.event_id,
        finding.file.file_name,
        finding_type,
        finding.value,
        finding.score,
        tag_str,
        description,
        pattern,
        index
    ))


def _scan_one(potential_file: PotentialFile, for_new_data: bool = False) -> int | list[Finding]:
    '''Scan a single file with the global recognizer and all the validators.
    
    Returns:
        - If db_path is set: number of findings written to the database (int)
        - If db_path is None: list of Finding objects (for single-process mode)
    '''
    try:
        profile_name = potential_file.profile_name(for_new_data)
        if profile_name is None or profile_name in (ProfileName.GENERIC, ProfileName.NULL, ProfileName.MISSING_IMAGE_TYPE):
            # Short circuit: not a recognized DICOM file (non-DICOM or unrecognized profile).
            # Do not add to report — we want only DICOM files in the report.
            # Do not check file size here — that applies only to recognized DICOM files.
            _logger.warning('🤷 Skipping file %s because it does not have a recognized profile (excluding from report)', potential_file)
            findings = []
        elif potential_file.file_size < MINIMUM_FILE_SIZE:
            # File size heuristic: only for recognized DICOM files; non-DICOM files are handled above
            _logger.warning('🤷 Skipping file %s because it is unexpectedly small', potential_file)
            humanized = humanize.naturalsize(potential_file.file_size)
            findings = [ErrorFinding(
                file=potential_file,
                value=f'FAIL! File is unexpectedly small ({humanized})',
                score=1.0,
                error_message=f'Skipping file because it is unexpectedly small; file size is {potential_file.file_size} bytes but require a minimum of {MINIMUM_FILE_SIZE} bytes'
            )]
        # See https://github.com/EDRN/jpl.labcas.validation/issues/31#issuecomment-4256524804;
        # These should not be skipped … not sure why the spreadsheet even calls them out
        # elif profile_name in (ProfileName.MR_LOC, ProfileName.MR_LOC_NEW) and (potential_file.rows < MINIMUM_MR_LOC_ROWS or potential_file.columns < MINIMUM_MR_LOC_COLUMNS):
        #     _logger.warning('🖼️ Skipping file %s because it is a small matrix helper file', potential_file)
        #     findings = []
        else:
            # Okay, full validation time
            findings: set[Finding] = set()
            findings.update(_recognizer.recognize(potential_file))

            # And now to validate the tags against a chosen profile of validators
            profile = get_profile(profile_name)
            findings.update(profile.validate(potential_file))        
            findings = list(findings)

        if _db_path is None:
            # Single-process mode: return findings directly
            return findings
        
        # Multi-process mode: write findings to database
        if findings:
            # Serialize writes across all worker processes so only one writes at a time
            with _db_lock:
                conn = sqlite3.connect(_db_path, timeout=30.0)
                try:
                    conn.execute('PRAGMA journal_mode=WAL')
                    for finding in findings:
                        _write_finding_to_db(conn, finding)
                    conn.commit()
                    return len(findings)
                finally:
                    conn.close()
        return 0
    except pydicom.errors.InvalidDicomError as ex:
        _logger.error('🤷 Ignoring invalid DICOM file: %s', potential_file)
        return [] if _db_path is None else 0
    except IOError as ex:
        _logger.error('💥 Problem reading file %s: %s', potential_file, ex)
        return [] if _db_path is None else 0
    except Exception as ex:
        _logger.error('💥 Unexpected error processing file %s: %s', potential_file, ex)
        _logger.error(traceback.format_exc())
        return [] if _db_path is None else 0


def _create_findings_db(db_path: str):
    '''Create the findings database schema.'''
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                site_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                finding_type TEXT NOT NULL,
                value TEXT NOT NULL,
                score REAL NOT NULL,
                tag TEXT,
                description TEXT,
                pattern TEXT,
                index_val INTEGER
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_file_path ON findings(file_path)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_site_event ON findings(site_id, event_id)')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.commit()
    finally:
        conn.close()


def validate_pool(
    recognizer_name: str, args: argparse.Namespace, concurrency: int, file_generator,
    for_new_data: bool = False
) -> tuple[str, int]:
    '''Validate the DICOM files using a pool of workers.
    
    The `file_generator` function is a callable that returns an iterable of paths to the
    DICOM files.
    
    Findings are written to a SQLite database by worker processes to reduce memory usage.
    
    Returns:
        Tuple of (database_path, total_findings_count)
    '''
    args_dict = vars(args)
    
    # Create a temporary SQLite database for findings
    db_file = tempfile.NamedTemporaryFile(prefix='labcas_validation_findings_', suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    _logger.info('📁 Using SQLite database for findings: %s', db_path)
    
    # Create the database schema
    _create_findings_db(db_path)
    
    # Use a process-shared lock from multiprocessing context instead of Manager().
    # This avoids spinning up a manager server process and related tempdir cleanup.
    ctx = get_context()
    db_write_lock = ctx.Lock()
    try:
        with ProcessPoolExecutor(
            max_workers=concurrency,
            initializer=_init_worker,
            initargs=(recognizer_name, args_dict, db_path, db_write_lock),
        ) as executor:
            futures = (executor.submit(_scan_one, p, for_new_data) for p in file_generator())
            total_findings = 0
            try:
                for future in as_completed(futures, timeout=None):
                    count = future.result()
                    total_findings += count
            except KeyboardInterrupt:
                # executor will clean up children on context exit
                pass
        
        _logger.info('📊 Processed %d findings, stored in database', total_findings)
        return db_path, total_findings
    except Exception as ex:
        # Clean up database on error
        try:
            os.remove(db_path)
        except Exception:
            pass
        raise


def validate_single(
    recognizer_name: str, args: argparse.Namespace, file_generator, for_new_data: bool = False
) -> list[Finding]:
    '''Validate the DICOM files using in the current process.
    
    The `file_generator` function is a callable that returns an iterable of paths to the DICOM
    files.
    '''
    _init_worker(recognizer_name, vars(args), db_path=None)  # No database for single-process mode
    results: list[Finding] = []
    for path in file_generator():
        findings = _scan_one(path, for_new_data)
        if isinstance(findings, list):
            results.extend(findings)
    return results


def _create_non_solr_paths_iterator(directory: str):
    '''Create a function that iterates over the paths in the given directory.'''
    _logger.info('🔍 Creating non-Solr paths iterator for %s', directory)

    def _iterate() -> Iterable[PotentialFile]:
        for path in iterate_paths(directory):
            yield PotentialFile(path)
    return _iterate


def _create_solr_paths_iterator(solr_url: str, directory: str, batch_size: int = 100):
    '''Create a function that iterates over the paths in the given directory using the given Solr URL.'''
    _logger.info('🔍 Creating Solr paths iterator for %s with batch size %d', directory, batch_size)

    def _collect_existing_paths(solr: pysolr.Solr, ids_to_paths: dict[str, str]) -> set[PotentialFile]:
        if not ids_to_paths:
            return set()
        # Build a single query that checks all IDs in this batch
        quoted_ids = ' OR '.join(f'"{file_id}"' for file_id in ids_to_paths.keys())
        query = f'id:({quoted_ids})'
        results = solr.search(query, sort='id asc', rows=len(ids_to_paths), fl=['id', 'eventID', 'BlindedSiteID'])
        existing_paths: set[PotentialFile] = set()
        for doc in results.docs:
            doc_id, event_id, site_id = doc.get('id'), doc.get('eventID', ['«unknown event»'])[0], doc.get('BlindedSiteID', ['«unknown site»'])[0]
            if isinstance(doc_id, list):
                doc_id = doc_id[0] if doc_id else None
            if doc_id and doc_id in ids_to_paths:
                existing_paths.add(PotentialFile(ids_to_paths[doc_id], site_id=site_id, event_id=event_id))
        return existing_paths

    collection_name = os.path.basename(directory)
    solr = pysolr.Solr(solr_url, verify=False)
    paths: set[PotentialFile] = set()
    batch: dict[str, str] = {}

    # First pass to populate `paths` with files both in the filesystem and in Solr
    for path in iterate_paths(directory):
        try:
            collection_index = path.index(collection_name)
        except ValueError:
            _logger.debug('⚠️ Skipping %s because it does not contain collection name %s', path, collection_name)
            continue
        file_id = path[collection_index:]
        batch[file_id] = path
        if len(batch) >= batch_size:
            paths.update(_collect_existing_paths(solr, batch))
            batch.clear()

    # Pick up any remaining files in the last batch
    if batch: paths.update(_collect_existing_paths(solr, batch))

    _logger.info('🔍 Found %d paths in both the filesystem at %s and in Solr %s', len(paths), directory, solr_url)
    def _iterate() -> Iterable[PotentialFile]:
        for path in paths:
            yield path
    return _iterate


def main():
    '''Main entry point to get the show on the road.'''
    recognizer_help_lines = ['PHI/PII Recognizers:']
    for name, recognizer_class in PHI_PII_RECOGNIZERS.items():
        marker = ' (default)' if name == DEFAULT_PHI_PII_RECOGNIZER else ''
        recognizer_help_lines.append(f'• {name}{marker}: {recognizer_class.description}')
    
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='\n'.join(recognizer_help_lines),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    add_standard_argparse_options(parser)
    parser.add_argument(
        '-s', '--score', type=_score_type, default=PHI_PII_THRESHOLD,
        help='Maximum PHI/PII score between 0.0 and 1.0, defaults to %(default)f; not all recognizers use a score, so this is optional'
    )
    parser.add_argument(
        '-c', '--concurrency', type=int, default=cpu_count(), help='Number of concurrent processes, defaults to %(default)d'
    )
    parser.add_argument(
        '-r', '--recognizer', choices=PHI_PII_RECOGNIZERS.keys(), default=DEFAULT_PHI_PII_RECOGNIZER,
        help='PHI/PII recognizer to use (see recognizer descriptions below)'
    )
    parser.add_argument(
        '-u', '--url', help='URL to LabCAS Solr (optional; if not provided, files will not be confirmed published)'
    )
    parser.add_argument(
        '-o', '--output', default='.', help='Output directory for CSV files (defaults to the current directory)'
    )
    parser.add_argument(
        '-n', '--new-data', action='store_true', help='Scan for new data (subject to stricter checks; default False)'
    )
    parser.add_argument(
        '--list-profiles',
        action='store_true',
        help='Print all known validation profiles and exit (no scan)',
    )
    parser.add_argument('directory', nargs='?', help='Directory to scan for DICOM files which typically ends in a collection name like "Prostate_MRI"')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel, format='%(levelname)s %(message)s')
    if args.list_profiles:
        for name in sorted(PROFILES.keys(), key=lambda n: n.value):
            print(PROFILES[name], end='\n\n')
        sys.exit(0)
    _logger.info('🧵 Multiprocessing start method: %s', get_context().get_start_method())
    output_directory = args.output.strip()
    os.makedirs(output_directory, exist_ok=True)
    if args.url:
        solr_url = args.url.strip()
        solr_url = solr_url if solr_url.endswith('/') else solr_url + '/'
        if 'files' not in solr_url:
            solr_url += 'files/'
        _logger.info('🔍 Solr URL is %s', solr_url)
        file_generator = _create_solr_paths_iterator(solr_url, args.directory)
    else:
        _logger.info('🔍 Not using Solr (no URL provided)')
        solr_url = None
        file_generator = _create_non_solr_paths_iterator(args.directory)

    db_path = None
    if not args.directory:
        _logger.error('💥 No directory provided')
        sys.exit(1)
    else:
        check_directory(args.directory)
        _logger.info('🔍 Scanning directory: %s', args.directory)
        try:
            if args.concurrency == 1:
                findings = validate_single(args.recognizer, args, file_generator, args.new_data)
                _logger.info('🔍 Found %d findings', len(findings))
                report = Report(findings=findings, score=args.score)
            else:
                db_path, total_findings = validate_pool(
                    args.recognizer, args, args.concurrency, file_generator, args.new_data
                )
                _logger.info('🔍 Found %d findings', total_findings)
                report = Report(db_path=db_path, score=args.score)
                _logger.info('🔍 Wrote database in: %s', db_path)
            report.generate_report(output_directory, for_new_data=args.new_data)
        finally:
            if db_path:
                try:
                    os.remove(db_path)
                except OSError as ex:
                    _logger.warning('⚠️ Could not remove temporary findings database %s: %s', db_path, ex)
        
    sys.exit(0)

if __name__ == '__main__':
    main()
