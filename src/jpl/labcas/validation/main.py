# encoding: utf-8

'''🛂 EDRN DICOM Validation.

Scans a folder of DICOM files and checks for PHI/PII (or as Heather likes to call it, "de-id", which
is clumsy as you're checking if de-identification happened by evidence of finding PHI or PII), and also
checks compliance with the EDRN core and MR requirements for DICOM tags.
'''

from . import VERSION
from ._argparse import add_standard_argparse_options
from ._classes import Finding, Report, ErrorFinding
from ._functions import check_directory
from .const import PHI_PII_THRESHOLD, DEFAULT_PROTOCOL
from .phi_pii_recognizers import PHI_PII_RECOGNIZERS, DEFAULT_PHI_PII_RECOGNIZER
from .validators import VALIDATORS
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import argparse, sys, logging, os, pydicom


def _score_type(value: str) -> float:
    '''Validate that the score is between 0.0 and 1.0 (inclusive).'''
    try:
        score = float(value)
        if not (0.0 <= score <= 1.0):
            raise argparse.ArgumentTypeError(f'{value} is not in the range [0.0, 1.0]')
        return score
    except ValueError:
        raise argparse.ArgumentTypeError(f'{value} is not a valid floating point number')


__doc__ = '🛂 EDRN DICOM Validation: check for PHI/PII and compliance with EDRN core and MR requirements for DICOM tags'
__copyright__ = 'Copyright © 2025 California Institute of Technology'
__license__ = 'Apache 2.0'


_recognizer = None  # The one recognizer we'll need for all workers for all files
_logger = logging.getLogger(__name__)


def _init_worker(recognizer_name: str, recognizer_args: dict):
    '''Initialize the worker by instantiating the global recognizer by name and its needed arguments.'''
    global _recognizer
    # Configure logging for this worker process to match the parent process
    logging.basicConfig(level=recognizer_args.get('loglevel', logging.INFO), format='%(levelname)s %(message)s')
    _recognizer = PHI_PII_RECOGNIZERS[recognizer_name](argparse.Namespace(**recognizer_args))


def _scan_one(path: str) -> list[Finding]:
    '''Scan a single file with the global recognizer.'''
    try:
        # We need the pixel data because we also do OCR to see if there's PHI/PII burnt into the image
        ds = pydicom.dcmread(path, stop_before_pixels=False, force=False)
        findings: list[Finding] = []
        findings.extend(_recognizer.recognize(ds))
        for validator in VALIDATORS:
            findings.extend(validator.validate(ds))
        return findings
    except pydicom.errors.InvalidDicomError as ex:
        _logger.error('🤷 Ignoring invalid DICOM file: %s', path)
        # This produces a lot of noise in the report so for now we'll just report nothing
        # return [ErrorFinding(file=path, value='🤷 Not a DICOM file', error_message=str(ex))]
        return []
    except IOError as ex:
        _logger.error('💥 Problem reading file %s: %s', path, ex)
        return []


def _iter_paths(root: str):
    '''Iterate over the paths in the given directory.

    We can't assume DICOM files end in .dcm; a lot of them come in without extensions, so process every file.
    '''
    for r, _, files in os.walk(root):
        for f in files:
            yield os.path.join(r, f)


def validate_pool(directory: str, recognizer_name: str, args: argparse.Namespace, concurrency: int) -> list[Finding]:
    '''Validate the DICOM files in the given directory using a pool of workers.'''
    args_dict = vars(args)
    results: list[Finding] = []
    with ProcessPoolExecutor(
        max_workers=concurrency,
        initializer=_init_worker,
        initargs=(recognizer_name, args_dict),
    ) as executor:
        futures = (executor.submit(_scan_one, p) for p in _iter_paths(directory))
        try:
            for future in as_completed(futures, timeout=None):
                res = future.result()
                if res: results.extend(res)
        except KeyboardInterrupt:
            # executor will clean up children on context exit
            pass
    return results


def validate_single(directory: str, recognizer_name: str, args: argparse.Namespace) -> list[Finding]:
    '''Validate the DICOM files in the given directory using in the current process.'''
    _init_worker(recognizer_name, vars(args))
    results: list[Finding] = []
    for path in _iter_paths(directory):
        results.extend(_scan_one(path))
    return results


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
    parser.add_argument('-p', '--protocol', type=int, default=DEFAULT_PROTOCOL, help='Protocol ID, defaults %(default)d')
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
        '-o', '--output', default='report.md', help='Output file for the report, defaults to %(default)s'
    )
    parser.add_argument('directory', help='Directory to scan for DICOM files')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel, format='%(levelname)s %(message)s')
    check_directory(args.directory)
    if args.concurrency == 1:
        findings = validate_single(args.directory, args.recognizer, args)
    else:
        findings = validate_pool(args.directory, args.recognizer, args, args.concurrency)
    _logger.info('🔍 Found %d findings', len(findings))
    report = Report(findings, args.output, args.score)
    report.generate_report()
    sys.exit(0)

if __name__ == '__main__':
    main()
