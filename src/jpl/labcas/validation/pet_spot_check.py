# encoding: utf-8

'''🛂 EDRN DICOM Validation: PET radiopharmaceutical tag spot-check.

Inspects PET DICOM files for RadiopharmaceuticalInformationSequence (0054,0016) and
reports whether required PET tags exist at the dataset root vs nested inside the
sequence.  See https://github.com/EDRN/jpl.labcas.validation/issues/53
'''

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
import argparse, json, logging, os, sys

import pydicom
from pydicom import datadict
from pydicom.dataelem import DataElement, convert_raw_data_element
from pydicom.sequence import Sequence as DICOMSequence

from ._argparse import add_standard_argparse_options
from ._functions import iterate_paths, textify_dicom_value


__doc__ = '🛂 Spot-check PET radiopharmaceutical tags at root vs inside (0054,0016)'
_logger = logging.getLogger(__name__)

_PET_SOP_CLASS_PREFIX = '1.2.840.10008.5.1.4.1.1.128'
_radiopharmaceutical_info_sequence_tag = pydicom.tag.Tag((0x0054, 0x0016))

_INSPECTED_TAGS: tuple[pydicom.tag.Tag, ...] = (
    pydicom.tag.Tag((0x0018, 0x1074)),  # RadionuclideTotalDose
    pydicom.tag.Tag((0x0018, 0x1075)),  # RadionuclideHalfLife
    pydicom.tag.Tag((0x0018, 0x1072)),  # RadiopharmaceuticalStartTime
    pydicom.tag.Tag((0x0018, 0x1078)),  # RadiopharmaceuticalStartDateTime
)

_REQUIRED_TAGS: tuple[pydicom.tag.Tag, ...] = (
    pydicom.tag.Tag((0x0018, 0x1074)),
    pydicom.tag.Tag((0x0018, 0x1075)),
    pydicom.tag.Tag((0x0018, 0x1072)),
)
_start_datetime_tag = pydicom.tag.Tag((0x0018, 0x1078))


@dataclass
class TagLocation:
    '''Presence and value of a tag at one location in a DICOM dataset.'''

    present: bool
    value: str | None = None


@dataclass
class TagInspection:
    '''Root vs nested presence for a single DICOM tag.'''

    tag: str
    keyword: str
    root: TagLocation
    nested: TagLocation


@dataclass
class FileInspection:
    '''Spot-check results for one DICOM file.'''

    path: str
    file_name: str
    instance_number: int | None
    modality: str
    sequence_item_count: int
    tags: list[TagInspection] = field(default_factory=list)


@dataclass
class SeriesInspection:
    '''Spot-check results for one PET series.'''

    series_instance_uid: str
    instance_count: int
    modality: str
    samples: list[FileInspection] = field(default_factory=list)
    conclusion: str = ''
    conclusion_detail: str = ''


def _get_sequence(ds: pydicom.Dataset, tag: pydicom.tag.Tag) -> DICOMSequence | None:
    '''Return a converted sequence value from the dataset, or None if absent.'''
    elem = ds.get_item(tag)
    if elem is None:
        return None
    if not isinstance(elem, DataElement):
        elem = convert_raw_data_element(elem)
    value = elem.value
    return value if isinstance(value, DICOMSequence) else None


def _format_tag_value(value: Any) -> str | None:
    '''Return a display string for a DICOM element value, or None when empty.'''
    parts = [v.strip() for v in textify_dicom_value(value) if v.strip()]
    if not parts:
        return None
    return ', '.join(parts)


def _tag_location(ds: pydicom.Dataset, tag: pydicom.tag.Tag) -> TagLocation:
    '''Return whether a tag is present on the dataset and its display value.'''
    elem = ds.get(tag)
    if elem is None:
        return TagLocation(present=False)
    value = _format_tag_value(elem.value)
    if value is None:
        return TagLocation(present=False)
    return TagLocation(present=True, value=value)


def _nested_tag_location(ds: pydicom.Dataset, tag: pydicom.tag.Tag) -> TagLocation:
    '''Return whether a tag is present in (0054,0016)[0] and its display value.'''
    sequence = _get_sequence(ds, _radiopharmaceutical_info_sequence_tag)
    if not sequence:
        return TagLocation(present=False)
    elem = sequence[0].get(tag)
    if elem is None:
        return TagLocation(present=False)
    value = _format_tag_value(elem.value)
    if value is None:
        return TagLocation(present=False)
    return TagLocation(present=True, value=value)


def _is_pet_file(path: str) -> bool:
    '''Return True when the file is a PET Image Storage instance.'''
    try:
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
    except Exception as ex:
        _logger.debug('Skipping unreadable file %s: %s', path, ex)
        return False
    sop_class = str(ds.get('SOPClassUID', ''))
    return sop_class.startswith(_PET_SOP_CLASS_PREFIX)


def _read_pet_header(path: str) -> pydicom.Dataset | None:
    '''Read DICOM metadata for a PET file, returning None on failure.'''
    try:
        return pydicom.dcmread(path, stop_before_pixels=True, force=True)
    except Exception as ex:
        _logger.warning('Could not read %s: %s', path, ex)
        return None


def _discover_pet_files(root: str) -> list[str]:
    '''Walk a directory tree and return paths to PET DICOM files.'''
    pet_files: list[str] = []
    for path in iterate_paths(root):
        if not os.path.isfile(path):
            continue
        if _is_pet_file(path):
            pet_files.append(path)
    return pet_files


def _instance_sort_key(path: str) -> tuple[int, str]:
    '''Sort PET instances by InstanceNumber, falling back to file name.'''
    ds = _read_pet_header(path)
    if ds is None:
        return (sys.maxsize, os.path.basename(path))
    raw = ds.get('InstanceNumber')
    try:
        instance_number = int(raw) if raw is not None else sys.maxsize
    except (TypeError, ValueError):
        instance_number = sys.maxsize
    return (instance_number, os.path.basename(path))


def _pick_sample_indices(count: int, sample_count: int) -> list[int]:
    '''Return evenly spaced indices for sampling up to sample_count items.'''
    if count <= 0:
        return []
    if count <= sample_count:
        return list(range(count))
    if sample_count == 1:
        return [0]
    step = (count - 1) / (sample_count - 1)
    return [round(i * step) for i in range(sample_count)]


def _pick_samples(sorted_paths: list[str], sample_count: int) -> list[str]:
    '''Pick evenly spaced sample files from a sorted instance list.'''
    indices = _pick_sample_indices(len(sorted_paths), sample_count)
    return [sorted_paths[i] for i in indices]


def _inspect_file(path: str) -> FileInspection | None:
    '''Inspect one PET file for root vs nested tag presence.'''
    ds = _read_pet_header(path)
    if ds is None:
        return None

    sequence = _get_sequence(ds, _radiopharmaceutical_info_sequence_tag)
    raw_instance = ds.get('InstanceNumber')
    try:
        instance_number = int(raw_instance) if raw_instance is not None else None
    except (TypeError, ValueError):
        instance_number = None

    tags: list[TagInspection] = []
    for tag in _INSPECTED_TAGS:
        tags.append(TagInspection(
            tag=str(tag),
            keyword=datadict.keyword_for_tag(tag) or '',
            root=_tag_location(ds, tag),
            nested=_nested_tag_location(ds, tag),
        ))

    return FileInspection(
        path=path,
        file_name=os.path.basename(path),
        instance_number=instance_number,
        modality=str(ds.get('Modality', 'UNKNOWN')),
        sequence_item_count=len(sequence) if sequence else 0,
        tags=tags,
    )


def _start_time_present(sample: FileInspection, location: str) -> bool:
    '''Return True when start time or start datetime is present at root or nested.'''
    for inspected in sample.tags:
        if inspected.keyword not in ('RadiopharmaceuticalStartTime', 'RadiopharmaceuticalStartDateTime'):
            continue
        loc = inspected.root if location == 'root' else inspected.nested
        if loc.present:
            return True
    return False


def _required_tag_present(sample: FileInspection, tag: pydicom.tag.Tag, location: str) -> bool:
    '''Return whether a required tag (or its start-time alternate) is present.'''
    if tag == _start_datetime_tag:
        return False
    if tag == pydicom.tag.Tag((0x0018, 0x1072)):
        return _start_time_present(sample, location)

    keyword = datadict.keyword_for_tag(tag)
    for inspected in sample.tags:
        if inspected.keyword == keyword:
            loc = inspected.root if location == 'root' else inspected.nested
            return loc.present
    return False


def _conclude_series(samples: list[FileInspection]) -> tuple[str, str]:
    '''Derive a series-level conclusion from inspected sample files.'''
    if not samples:
        return 'NO_SAMPLES', 'No readable PET sample files were inspected.'

    all_root = all(
        _required_tag_present(sample, tag, 'root')
        for sample in samples
        for tag in _REQUIRED_TAGS
    )
    if all_root:
        return (
            'PRESENT_AT_ROOT',
            'Required PET tags are present at the dataset root on all inspected samples; '
            'the validator should already see them.',
        )

    all_nested = all(
        _required_tag_present(sample, tag, 'nested')
        for sample in samples
        for tag in _REQUIRED_TAGS
    )
    any_root = any(
        _required_tag_present(sample, tag, 'root')
        for sample in samples
        for tag in _REQUIRED_TAGS
    )
    any_nested = any(
        _required_tag_present(sample, tag, 'nested')
        for sample in samples
        for tag in _REQUIRED_TAGS
    )

    if all_nested and not any_root:
        return (
            'LIKELY_VALIDATOR_PARSING_ISSUE',
            'Required PET tags exist inside RadiopharmaceuticalInformationSequence on all '
            'inspected samples but are absent at the dataset root; the validator likely '
            'needs to traverse nested PET metadata.',
        )

    if not any_root and not any_nested:
        return (
            'LIKELY_METADATA_LIMITATION',
            'Required PET tags are absent at both the dataset root and inside '
            'RadiopharmaceuticalInformationSequence across all inspected samples; '
            'this is likely a legacy export metadata limitation.',
        )

    differing = [
        sample.file_name
        for sample in samples
        if not all(_required_tag_present(sample, tag, 'nested') for tag in _REQUIRED_TAGS)
        or any(_required_tag_present(sample, tag, 'root') for tag in _REQUIRED_TAGS)
    ]
    return (
        'INCONSISTENT_WITHIN_SERIES',
        'Inspected samples disagree on where required PET tags are stored'
        + (f' (see {", ".join(differing)})' if differing else '')
        + '.',
    )


def _group_by_series(paths: list[str]) -> dict[str, list[str]]:
    '''Group PET file paths by SeriesInstanceUID.'''
    series: dict[str, list[str]] = {}
    for path in paths:
        ds = _read_pet_header(path)
        if ds is None:
            continue
        uid = str(ds.get('SeriesInstanceUID', ''))
        if not uid:
            uid = f'«unknown-series:{path}»'
        series.setdefault(uid, []).append(path)
    for uid in series:
        series[uid].sort(key=_instance_sort_key)
    return series


def _inspect_series(
    series_instance_uid: str,
    paths: list[str],
    sample_count: int,
    explicit_only: bool,
) -> SeriesInspection:
    '''Inspect one PET series, sampling instances unless explicit_only is set.'''
    sample_paths = paths if explicit_only else _pick_samples(paths, sample_count)
    samples: list[FileInspection] = []
    modality = 'UNKNOWN'
    for path in sample_paths:
        inspection = _inspect_file(path)
        if inspection is None:
            continue
        samples.append(inspection)
        modality = inspection.modality

    conclusion, detail = _conclude_series(samples)
    return SeriesInspection(
        series_instance_uid=series_instance_uid,
        instance_count=len(paths),
        modality=modality,
        samples=samples,
        conclusion=conclusion,
        conclusion_detail=detail,
    )


def inspect_paths(paths: list[str], sample_count: int = 3) -> list[SeriesInspection]:
    '''Inspect PET files discovered from the given paths.'''
    discovered: list[str] = []
    explicit_files: list[str] = []
    has_directory = False

    for path in paths:
        if os.path.isdir(path):
            has_directory = True
            discovered.extend(_discover_pet_files(path))
        elif os.path.isfile(path):
            if _is_pet_file(path):
                explicit_files.append(path)
            else:
                _logger.warning('Skipping non-PET file: %s', path)
        else:
            _logger.warning('Path does not exist: %s', path)

    if has_directory:
        pet_files = sorted(set(discovered))
        explicit_only = False
    else:
        pet_files = sorted(set(explicit_files), key=_instance_sort_key)
        explicit_only = True

    if not pet_files:
        return []

    grouped = _group_by_series(pet_files)
    return [
        _inspect_series(uid, series_paths, sample_count, explicit_only)
        for uid, series_paths in sorted(grouped.items())
    ]


def _format_location(location: TagLocation) -> str:
    '''Format a tag location for human-readable output.'''
    if not location.present:
        return 'missing'
    return location.value or 'present'


def _print_human_report(results: list[SeriesInspection]) -> None:
    '''Print a human-readable spot-check report to stdout.'''
    if not results:
        print('No PET files found to inspect.')
        return

    for series in results:
        uid_display = series.series_instance_uid
        if len(uid_display) > 48:
            uid_display = uid_display[:45] + '...'
        print(
            f'Series {uid_display} '
            f'({series.instance_count} instances, Modality={series.modality})'
        )
        for sample in series.samples:
            instance = (
                f'InstanceNumber={sample.instance_number}'
                if sample.instance_number is not None
                else 'InstanceNumber=unknown'
            )
            print(f'  Sample {sample.file_name} ({instance}):')
            print(
                f'    (0054,0016) RadiopharmaceuticalInformationSequence: '
                f'root={"present" if sample.sequence_item_count else "missing"}'
                f' ({sample.sequence_item_count} item{"s" if sample.sequence_item_count != 1 else ""})'
            )
            for tag in sample.tags:
                label = f'{tag.tag} {tag.keyword}' if tag.keyword else tag.tag
                print(
                    f'    {label}: '
                    f'root={_format_location(tag.root)} | nested={_format_location(tag.nested)}'
                )
        print(f'  Conclusion: {series.conclusion}')
        print(f'  {series.conclusion_detail}')
        print()


def _to_json(results: list[SeriesInspection]) -> str:
    '''Serialize inspection results to JSON.'''

    def _convert(obj: Any) -> Any:
        if hasattr(obj, '__dataclass_fields__'):
            return {key: _convert(value) for key, value in asdict(obj).items()}
        if isinstance(obj, list):
            return [_convert(item) for item in obj]
        return obj

    return json.dumps(_convert(results), indent=2)


def main():
    '''Main entry point for the PET spot-check CLI.'''
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_standard_argparse_options(parser)
    parser.add_argument(
        '--samples',
        type=int,
        default=3,
        metavar='N',
        help='Number of instances to sample per series when scanning directories (default: 3)',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Print machine-readable JSON instead of a human-readable report',
    )
    parser.add_argument(
        'paths',
        nargs='+',
        help='Event directory, DICOM folder, or explicit PET file paths to inspect',
    )
    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel, format='%(levelname)s %(message)s')

    if args.samples < 1:
        _logger.error('--samples must be at least 1')
        sys.exit(1)

    results = inspect_paths(args.paths, sample_count=args.samples)

    if args.json:
        print(_to_json(results))
    else:
        _print_human_report(results)

    sys.exit(0)


if __name__ == '__main__':
    main()
