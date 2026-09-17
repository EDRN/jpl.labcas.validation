# encoding: utf-8

'''🛂 EDRN DICOM Validation: report summarizer.

Used to take all the numerous .csv reports from multiple collections and summarize
each collection into its own summary and PHI/PII CSV files.

To use this, first run

    mkdir /labcas-data/labcas-backend/reports/edrn/COLLECTION
    validate-dicom-files \
        --url https://localhost:8984/solr/ \
        --output /labcas-data/labcas-backend/reports/edrn/COLLECTION
        /labca-data/labcas-backend/archive/edrn/COLLECTION

On all the collections you want summarized; repeat for each COLLECTION.

Then run this script:

    summarize-validation-reports /labcas-data/labcas-backend/reports/edrn

That writes ``summary.csv`` and ``phi.csv`` into each collection folder under the
reports directory.
'''

import argparse, logging, csv, glob, os, os.path, re
from collections import defaultdict

_logger = logging.getLogger(__name__)
_series_removal_re = re.compile(r'\(with the same SeriesInstanceUID [^)]+\)')
_image_orientation_patient_removal_re = re.compile(r', «[^»]+», ')
_phi_pii_removal_re = re.compile(r'\), .+$')
_completeness_and_format_removal_re = re.compile(r'— please review for completeness and format')
_sample_value_removal_re = re.compile(r'(, )?«[^»]*»,?')

_OUTPUT_CSV_NAMES = frozenset({'summary.csv', 'phi.csv'})
_SUMMARY_CSV_HEADER = [
    'Issue', 'Profile', 'Total Files with this Issue', 'Percent of all Files',
    'Number of Sites with Issue',
]
_PHI_CSV_HEADER = [
    'Issue', 'Total Files with this Issue', 'Percent of all Files',
    'Number of Sites with Issue',
]


def _is_phi_pii_finding(finding: str) -> bool:
    '''Return True if the finding kind is a PHI/PII finding.

    Matches both header and burned-in pixel findings, including NBSP vs regular-space
    variants of the kind label.
    '''
    return 'PHI/PII' in finding


def _simplify_issue(finding: str, details: str) -> str:
    '''Simplify the issue description.

    The detailed reports in the input `.csv` files are verbose; we want to simplify the findings
    for the summary and to coalesce similar findings into a single issue.
    '''

    if 'Possible PHI/PII in Header' in finding:
        details = _phi_pii_removal_re.sub(") possible PHI/PII in tag's value", details)
    elif finding == '👮 Warning':
        details = 'Warning: ' + details
    elif 'Possible Burned-in PHI/PII (Pixels)' in finding:
        details = 'Possible burned-in PHI/PII (pixels)'
    elif details.startswith('(0018,0088)'):
        details = _series_removal_re.sub('', details)
    elif details.startswith('(0020,0037)'):
        details = _image_orientation_patient_removal_re.sub('', details)

    # Remove any found values so `(0008,0008) (ImageType), «Blah blah», Failed core…` and
    # `(0008,0008) (ImageType), «Goober goober», Failed core…` are treated the same
    details = _sample_value_removal_re.sub('', details)

    # Remove the utterly useless "please review for completeness and format" text that appears on
    # every single issue … le sigh!
    details = _completeness_and_format_removal_re.sub('', details)

    return details.strip()


def _unique_file_name(site: str, event: str, file_name: str) -> str:
    '''Make a quasi-unique file name within a collection.

    This just concatenates the site, event, and file name—separated by slashes.
    '''
    return f'{site}/{event}/{file_name}'


def _write_summary_csv(
    output_path: str,
    all_files: set[str],
    issue_by_files: defaultdict,
    issue_by_site: defaultdict,
    *,
    include_profile: bool,
):
    '''Write a summary CSV.

    When ``include_profile`` is True, rows are keyed by ``(issue, profile)`` and include a
    Profile column. When False (PHI/PII), rows are keyed by issue only.
    '''
    header = _SUMMARY_CSV_HEADER if include_profile else _PHI_CSV_HEADER
    with open(output_path, 'w', newline='') as io:
        writer = csv.writer(io)
        writer.writerow(header)
        for key in sorted(issue_by_files.keys()):
            files = issue_by_files[key]
            sites = issue_by_site[key]
            percentage = f'{len(files) / len(all_files):.2%}' if all_files else '0.00%'
            if include_profile:
                issue, profile = key
                writer.writerow([issue, profile, len(files), percentage, len(sites)])
            else:
                writer.writerow([key, len(files), percentage, len(sites)])


def _summarize_collection(collection_directory: str):
    '''Summarize one collection's site CSV reports into summary.csv and phi.csv.'''
    all_files: set[str] = set()
    summary_by_files: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    summary_by_site: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    phi_by_files: defaultdict[str, set[str]] = defaultdict(set)
    phi_by_site: defaultdict[str, set[str]] = defaultdict(set)

    for report_file in glob.iglob(os.path.join(collection_directory, '*.csv')):
        basename = os.path.basename(report_file)
        if basename in _OUTPUT_CSV_NAMES:
            continue
        with open(report_file, 'r', newline='') as io:
            reader = csv.reader(io)
            for row in reader:
                if not row or row[0] == 'Site ID':
                    continue
                site, event, file_name, _study_uid, _series_uid, profile, _score, finding, details = row
                unique_file_name = _unique_file_name(site, event, file_name)
                all_files.add(unique_file_name)
                issue = _simplify_issue(finding, details)
                if _is_phi_pii_finding(finding):
                    phi_by_files[issue].add(unique_file_name)
                    phi_by_site[issue].add(site)
                else:
                    key = (issue, profile)
                    summary_by_files[key].add(unique_file_name)
                    summary_by_site[key].add(site)

    assert len(summary_by_files) == len(summary_by_site)
    assert len(phi_by_files) == len(phi_by_site)

    _write_summary_csv(
        os.path.join(collection_directory, 'summary.csv'),
        all_files, summary_by_files, summary_by_site,
        include_profile=True,
    )
    _write_summary_csv(
        os.path.join(collection_directory, 'phi.csv'),
        all_files, phi_by_files, phi_by_site,
        include_profile=False,
    )
    _logger.info(
        'Wrote summary.csv (%d issues) and phi.csv (%d issues) for %s',
        len(summary_by_files), len(phi_by_files), collection_directory,
    )


def _summarize_reports(report_directory: str):
    '''Summarize each collection folder under the reports directory.'''
    for entry in sorted(os.listdir(report_directory)):
        collection_directory = os.path.join(report_directory, entry)
        if not os.path.isdir(collection_directory):
            continue
        site_csvs = [
            path for path in glob.glob(os.path.join(collection_directory, '*.csv'))
            if os.path.basename(path) not in _OUTPUT_CSV_NAMES
        ]
        if not site_csvs:
            _logger.debug('Skipping %s: no site CSV reports', collection_directory)
            continue
        _summarize_collection(collection_directory)


def main():
    '''Entrypoint for summarizing validation reports.'''
    parser = argparse.ArgumentParser(
        description='Summarize validation reports into per-collection summary.csv and phi.csv files.'
    )
    parser.add_argument(
        'report_directory', type=str,
        help="The directory containing the collections' validation report folders",
    )
    args = parser.parse_args()
    _summarize_reports(args.report_directory)


if __name__ == '__main__':
    main()
