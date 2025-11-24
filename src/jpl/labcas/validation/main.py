# encoding: utf-8

'''🛂 EDRN DICOM Validation.

Scans a folder of DICOM files and checks for PHI/PII (or as Heather likes to call it, "de-id", which
is clumsy as you're checking if de-identification happened by evidence of finding PHI or PII), and also
checks compliance with the EDRN core and MR requirements for DICOM tags.
'''

from . import VERSION
from ._argparse import add_standard_argparse_options
from ._classes import Finding, Report, ErrorFinding, PotentialFile
from ._functions import check_directory, iterate_paths
from .const import PHI_PII_THRESHOLD, IGNORED_FILES
from .phi_pii_recognizers import PHI_PII_RECOGNIZERS, DEFAULT_PHI_PII_RECOGNIZER
from .validators import VALIDATORS
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from typing import Iterable
import argparse, sys, logging, os, pydicom, pysolr, os.path



__doc__ = '🛂 EDRN DICOM Validation: check for PHI/PII and compliance with EDRN core and MR requirements for DICOM tags'
__copyright__ = 'Copyright © 2025 California Institute of Technology'
__license__ = 'Apache 2.0'
_recognizer = None  # The one recognizer we'll need for all workers for all files
_logger = logging.getLogger(__name__)


def _score_type(value: str) -> float:
    '''Validate that the score is between 0.0 and 1.0 (inclusive).'''
    try:
        score = float(value)
        if not (0.0 <= score <= 1.0):
            raise argparse.ArgumentTypeError(f'{value} is not in the range [0.0, 1.0]')
        return score
    except ValueError:
        raise argparse.ArgumentTypeError(f'{value} is not a valid floating point number')


def _init_worker(recognizer_name: str, recognizer_args: dict):
    '''Initialize the worker by instantiating the global recognizer by name and its needed arguments.'''
    global _recognizer
    # Configure logging for this worker process to match the parent process
    logging.basicConfig(level=recognizer_args.get('loglevel', logging.INFO), format='%(levelname)s %(message)s')
    _recognizer = PHI_PII_RECOGNIZERS[recognizer_name](argparse.Namespace(**recognizer_args))


def _scan_one(potential_file: PotentialFile) -> list[Finding]:
    '''Scan a single file with the global recognizer and all the validators.'''
    try:
        # We need the pixel data because we also do OCR to see if there's PHI/PII burnt into the image
        findings: list[Finding] = []
        findings.extend(_recognizer.recognize(potential_file))
        for validator in VALIDATORS:
            findings.extend(validator.validate(potential_file))

        return findings
    except pydicom.errors.InvalidDicomError as ex:
        _logger.error('🤷 Ignoring invalid DICOM file: %s', potential_file)
        # This produces a lot of noise in the report so for now we'll just report nothing
        # return [ErrorFinding(file=path, value='🤷 Not a DICOM file', error_message=str(ex))]
        return []
    except IOError as ex:
        _logger.error('💥 Problem reading file %s: %s', potential_file, ex)
        return []



def validate_pool(
    directory: str, recognizer_name: str, args: argparse.Namespace, concurrency: int, file_generator) -> list[Finding]:
    '''Validate the DICOM files in the given directory using a pool of workers.
    
    The `file_generator` function is a callable that returns an iterable of paths to the
    DICOM files in the given directory.
    '''
    args_dict = vars(args)
    results: list[Finding] = []
    with ProcessPoolExecutor(
        max_workers=concurrency,
        initializer=_init_worker,
        initargs=(recognizer_name, args_dict),
    ) as executor:
        futures = (executor.submit(_scan_one, p) for p in file_generator())
        try:
            for future in as_completed(futures, timeout=None):
                res = future.result()
                if res: results.extend(res)
        except KeyboardInterrupt:
            # executor will clean up children on context exit
            pass
    return results


def validate_single(directory: str, recognizer_name: str, args: argparse.Namespace, file_generator) -> list[Finding]:
    '''Validate the DICOM files in the given directory using in the current process.
    
    The `file_generator` function is a callable that returns an iterable of paths to the DICOM
    files in the given directory.
    '''
    _init_worker(recognizer_name, vars(args))
    results: list[Finding] = []
    for path in file_generator():
        results.extend(_scan_one(path))
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
        results = solr.search(query, rows=len(ids_to_paths), fl=['id', 'eventID'])
        existing_paths: set[PotentialFile] = set()
        for doc in results.docs:
            doc_id, event_id = doc.get('id'), doc.get('eventID', ['«unknown event»'])[0]
            if isinstance(doc_id, list):
                doc_id = doc_id[0] if doc_id else None
            if doc_id and doc_id in ids_to_paths:
                existing_paths.add(PotentialFile(ids_to_paths[doc_id], event_id=event_id))
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
        '-o', '--output', default='report.csv', help='Output file for the report, defaults to %(default)s'
    )
    parser.add_argument(
        '-u', '--url', help='URL to LabCAS Solr (optional; if not provided, files will not be confirmed published)'
    )
    parser.add_argument('directory', help='Directory to scan for DICOM files')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel, format='%(levelname)s %(message)s')
    check_directory(args.directory)
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

    if args.concurrency == 1:
        findings = validate_single(args.directory, args.recognizer, args, file_generator)
    else:
        findings = validate_pool(args.directory, args.recognizer, args, args.concurrency, file_generator)
    _logger.info('🔍 Found %d findings', len(findings))
    report = Report(findings, args.output, args.score)
    report.generate_report()
    sys.exit(0)

if __name__ == '__main__':
    main()
