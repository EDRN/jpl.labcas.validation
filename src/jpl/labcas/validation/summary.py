# encoding: utf-8

'''🛂 EDRN DICOM Validation: report summarizer.

Used to take all the numerous .csv reports from multiple collections together and summarize into a single report CSV file.

To use this, first run

    mkdir /labcas-data/labcas-backend/reports/edrn/COLLECTION
    validate-dicom-files \
        --url https://localhost:8984/solr/ \
        --output /labcas-data/labcas-backend/reports/edrn/COLLECTION
        /labca-data/labcas-backend/archive/edrn/COLLECTION

On all the collections you want summarized; repeat for each COLLECTION.

Then run this script:

    summarize-validation-reports /labcas-data/labcas-backend/reports/edrn
'''

from typing import Any
import argparse, logging, csv, glob, os.path, re
from collections import defaultdict, Counter

_logger = logging.getLogger(__name__)
_series_removal_re = re.compile(r'\(with the same SeriesInstanceUID [^)]+\)')
_image_orientation_patient_removal_re = re.compile(r', «[^»]+», ')
_phi_pii_removal_re = re.compile(r'\), .+$')
_completeness_and_format_removal_re = re.compile(r'— please review for completeness and format')
_sample_value_removal_re = re.compile(r'(, )?«[^»]*»,?')

def _simplify_issue(finding, details: str) -> str:
    '''Simplify the issue description.

    The detailed reports in the input `.csv` files are verbose; we want to simplify the findings
    for the summary and to coalesce similar findings into a single issue.
    '''

    if finding == '🙈 Possible PHI/PII in Header':
        details = _phi_pii_removal_re.sub(") possible PHI/PII in tag's value", details)
    elif finding == '👮 Warning':
        details = 'Warning: ' + details
    elif finding == '🖼️ Possible Burned-in PHI/PII (Pixels)':
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


def _unique_file_name(collection: str, site: str, event: str, file_name: str) -> str:
    '''Make a quasi-unique file name.

    This just concatenates the collection, site, event, and file name—separated by slashes.
    '''
    return f'{collection}/{site}/{event}/{file_name}'


def _get_collection_and_site_from_file_name(file_name: str) -> str:
    '''Get the collection and site from the file name.'''
    splatted = file_name.split('/')
    return f'{splatted[0]}: {splatted[1]}'


def _summarize_reports(report_directory: str, output: str):
    '''Summarize the validation reports into a single report CSV file.'''
    all_files: set[str] = set()
    issue_by_files: defaultdict[str, set[str]] = defaultdict(set)
    issue_by_collection: defaultdict[str, set[str]] = defaultdict(set)
    issue_by_site: defaultdict[str, set[str]] = defaultdict(set)
    # per_event_counts: defaultdict[str, Counter] = defaultdict(Counter)
    # total_events = total_files = total_findings = 0
    for report_file in glob.iglob(f'{report_directory}/*/*.csv'):
        collection = os.path.basename(os.path.dirname(report_file))
        with open(report_file, 'r', newline='') as io:
            reader = csv.reader(io)
            for row in reader:
                if row[0] == 'Site ID': continue
                site, event, file_name, score, finding, details = row
                unique_file_name = _unique_file_name(collection, site, event, file_name)
                all_files.add(unique_file_name)
                issue = _simplify_issue(finding, details)
                issue_by_files[issue].add(unique_file_name)
                issue_by_collection[issue].add(collection)
                issue_by_site[issue].add(site)
    assert len(issue_by_collection) == len(issue_by_files) == len(issue_by_site)

    with open(output, 'w', newline='') as io:
        writer = csv.writer(io)
        writer.writerow([
            'Issue', 'Total Files with this Issue', 'Percent of all Files', 'Colletions with this Issue',
            'Number of Sites with Issue', 'Collection+BlindedSiteIDs with Issue'
        ])
        for issue in sorted(issue_by_site.keys()):
            sites, collections, files = issue_by_site[issue], issue_by_collection[issue], issue_by_files[issue]
            collections = ', '.join(sorted(collections))
            col_sites = '; '.join(sorted(set([_get_collection_and_site_from_file_name(file) for file in files])))
            percentage = f'{len(files) / len(all_files):.2%}'
            writer.writerow([issue, len(files), percentage, collections, len(sites), col_sites])


def main():
    '''Entrypoint for summarizing validation reports.'''
    parser = argparse.ArgumentParser(description='Summarize validation reports into a single report CSV file.')
    parser.add_argument('--output', type=str, default='summary.csv', help='The output file name; defaults to "%(default)s"')
    parser.add_argument('report_directory', type=str, help="The directory containing the collections' validation report files")
    args = parser.parse_args()
    _summarize_reports(args.report_directory, args.output)


if __name__ == '__main__':
    main()
