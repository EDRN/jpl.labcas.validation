# encoding: utf-8

'''🛂 EDRN DICOM Validation: per-site summary report.

Reads the per-site CSV reports under ``REPORT_FOLDER/sites/`` and writes a
dc.png-style summary table (PNG, CSV, and Markdown) into ``REPORT_FOLDER``.
This creates the Dan Crichton (@dcrichto1) style summary report as detailed
in email and later as a comment in EDRN/EDRN-metadata#165.

Usage::

    summarize-site-reports [--title TITLE] REPORT_FOLDER

Example::

    summarize-site-reports --title "LTP2 Validation Summary Report" reports/Lung_Team_Project_2

Columns C–F are percentages of distinct Event IDs that have at least one
finding of that type. ``👮 Warning`` rows are ignored entirely.
'''

from __future__ import annotations

import argparse
import csv
import glob
import logging
import os
import os.path
import sys
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

__doc__ = (
    '🛂 EDRN DICOM Validation: summarize per-site CSV reports into a '
    'Validation Summary Report (PNG, CSV, Markdown), @dcrichto1 style'
)
__copyright__ = 'Copyright © 2025–2026 California Institute of Technology'
__license__ = 'Apache 2.0'

_logger = logging.getLogger(__name__)

_DEFAULT_TITLE = 'Validation Summary Report'
_PNG_NAME = 'Validation_Summary_Report.png'
_CSV_NAME = 'validation_summary.csv'
_MD_NAME = 'validation_summary.md'

# Finding labels as emitted by the validator. Match after normalising NBSP → space.
_FINDING_MISSING = '⚠️ Missing Required Tags'
_FINDING_ERROR = '❌ Error'
_FINDING_HEADER = '🙈 Possible PHI/PII in Header'
_FINDING_BURNED = '🖼️ Possible Burned-in PHI/PII (Pixels)'
_CATEGORY_KEYS = ('missing', 'error', 'header', 'burned')
_FINDING_TO_CATEGORY = {
    _FINDING_MISSING: 'missing',
    _FINDING_ERROR: 'error',
    _FINDING_HEADER: 'header',
    _FINDING_BURNED: 'burned',
}

_CSV_HEADER = [
    'BlindedSiteID',
    'TotalEventIDs',
    'MissingRequiredTags_EventIDs',
    'MissingRequiredTags_Pct',
    'CriticalErrors_EventIDs',
    'CriticalErrors_Pct',
    'HeaderIdentifiers_EventIDs',
    'HeaderIdentifiers_Pct',
    'BurnedInIdentifiers_EventIDs',
    'BurnedInIdentifiers_Pct',
]


@dataclass
class SiteStats:
    '''Aggregated stats for one site CSV.'''

    site_id: str
    event_ids: set[str] = field(default_factory=set)
    affected: dict[str, set[str]] = field(
        default_factory=lambda: {key: set() for key in _CATEGORY_KEYS}
    )
    file_keys: set[str] = field(default_factory=set)
    pet_file_keys: set[str] = field(default_factory=set)

    @property
    def total_events(self) -> int:
        return len(self.event_ids)

    @property
    def pet_files(self) -> int:
        return len(self.pet_file_keys)

    def affected_count(self, category: str) -> int:
        return len(self.affected[category])

    def affected_pct(self, category: str) -> float:
        total = self.total_events
        if total == 0:
            return 0.0
        return 100.0 * self.affected_count(category) / total


@dataclass
class ReportStats:
    '''Aggregated stats across all sites in a report folder.'''

    sites: list[SiteStats]
    total_files: int

    @property
    def total_sites(self) -> int:
        return len(self.sites)

    @property
    def total_events(self) -> int:
        return sum(site.total_events for site in self.sites)

    def affected_count(self, category: str) -> int:
        return sum(site.affected_count(category) for site in self.sites)

    def affected_pct(self, category: str) -> float:
        total = self.total_events
        if total == 0:
            return 0.0
        return 100.0 * self.affected_count(category) / total


def _normalize_finding(finding: str) -> str:
    '''Normalise NBSP and other whitespace so finding labels match reliably.'''
    return finding.replace('\u00a0', ' ').strip()


def _unique_file_name(site: str, event: str, file_path: str) -> str:
    '''Make a quasi-unique file name within a collection (site/event/path).'''
    return f'{site}/{event}/{file_path}'


def _format_pct(pct: float) -> str:
    '''Format a percentage to two decimal places with a % sign.'''
    return f'{pct:.2f}%'


def _format_count_pct(count: int, pct: float) -> str:
    '''Format ``n (x.xx%)`` for display in PNG/Markdown.'''
    return f'{count} ({_format_pct(pct)})'


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    '''Load a TrueType font, falling back to Pillow's default.

    Prefer Arial, then Helvetica Neue / Helvetica / Roboto / DejaVu / Liberation.
    Entries are ``(path, ttc_index)``; use index 0 for single-face ``.ttf`` files.
    '''
    # Helvetica Neue.ttc: 0=Regular, 1=Bold; Helvetica.ttc: 0=Regular, 1=Bold
    face = 1 if bold else 0
    candidates = [
        ('/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf', 0),
        ('/Library/Fonts/Arial Bold.ttf' if bold else '/Library/Fonts/Arial.ttf', 0),
        ('/System/Library/Fonts/HelveticaNeue.ttc', face),
        ('/System/Library/Fonts/Helvetica.ttc', face),
        ('/Library/Fonts/Roboto-Bold.ttf' if bold else '/Library/Fonts/Roboto-Regular.ttf', 0),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 0),
        ('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 0),
    ]
    for path, index in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size=size, index=index)
            except OSError:
                continue
    return ImageFont.load_default()


def _aggregate_site_csv(csv_path: str) -> SiteStats:
    '''Stream one site CSV and collect Event ID / finding / file stats.'''
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    stats = SiteStats(site_id=stem)

    with open(csv_path, 'r', newline='', encoding='utf-8', errors='replace') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            site_id = (row.get('Site ID') or '').strip()
            event_id = (row.get('Event ID') or '').strip()
            file_path = (row.get('File Path') or '').strip()
            finding = _normalize_finding(row.get('Findings') or '')
            # Column F in the site CSV header is Profile.
            profile = (row.get('Profile') or '').strip()

            if not event_id:
                continue

            if site_id and site_id != stats.site_id:
                # Prefer the Site ID column when present and consistent.
                stats.site_id = site_id

            stats.event_ids.add(event_id)
            if site_id and event_id and file_path:
                file_key = _unique_file_name(site_id, event_id, file_path)
                stats.file_keys.add(file_key)
                if 'PET' in profile:
                    stats.pet_file_keys.add(file_key)

            category = _FINDING_TO_CATEGORY.get(finding)
            if category is not None:
                stats.affected[category].add(event_id)
            # Warnings and any other finding types are ignored for columns C–F.

    if stats.site_id != stem:
        _logger.warning(
            'Site ID %r in %s differs from filename stem %r; using Site ID column',
            stats.site_id, csv_path, stem,
        )
    return stats


def _validate_report_folder(report_folder: str) -> str:
    '''Validate REPORT_FOLDER/sites/ and return the sites directory path.

    Exits the process with a clear error if the folder, sites subfolder, or
    site CSV files are missing.
    '''
    if not os.path.isdir(report_folder):
        _logger.error('💥 Report folder does not exist or is not a directory: %s', report_folder)
        sys.exit(1)

    sites_dir = os.path.join(report_folder, 'sites')
    if not os.path.isdir(sites_dir):
        _logger.error(
            '💥 Expected a sites/ subfolder under %s (looked for %s)',
            report_folder, sites_dir,
        )
        sys.exit(1)

    site_csvs = sorted(glob.glob(os.path.join(sites_dir, '*.csv')))
    if not site_csvs:
        _logger.error('💥 No site CSV files found in %s', sites_dir)
        sys.exit(1)

    return sites_dir


def aggregate_report(report_folder: str) -> ReportStats:
    '''Aggregate all site CSVs under REPORT_FOLDER/sites/.'''
    sites_dir = _validate_report_folder(report_folder)
    site_csvs = sorted(glob.glob(os.path.join(sites_dir, '*.csv')))
    sites: list[SiteStats] = []
    all_files: set[str] = set()

    for csv_path in site_csvs:
        _logger.info('📊 Aggregating %s', csv_path)
        site = _aggregate_site_csv(csv_path)
        sites.append(site)
        all_files.update(site.file_keys)

    # Stable, readable order: alphabetical by Site ID.
    sites.sort(key=lambda s: s.site_id.lower())
    return ReportStats(sites=sites, total_files=len(all_files))


def _site_csv_row(site: SiteStats) -> list:
    '''Build one CSV data row for a site.'''
    return [
        site.site_id,
        site.total_events,
        site.affected_count('missing'),
        _format_pct(site.affected_pct('missing')),
        site.affected_count('error'),
        _format_pct(site.affected_pct('error')),
        site.affected_count('header'),
        _format_pct(site.affected_pct('header')),
        site.affected_count('burned'),
        _format_pct(site.affected_pct('burned')),
    ]


def _grand_total_csv_row(stats: ReportStats) -> list:
    '''Build the Grand Total CSV row.'''
    return [
        'Grand Total',
        stats.total_events,
        stats.affected_count('missing'),
        _format_pct(stats.affected_pct('missing')),
        stats.affected_count('error'),
        _format_pct(stats.affected_pct('error')),
        stats.affected_count('header'),
        _format_pct(stats.affected_pct('header')),
        stats.affected_count('burned'),
        _format_pct(stats.affected_pct('burned')),
    ]


def write_csv(stats: ReportStats, output_path: str) -> None:
    '''Write the machine-readable audit CSV.'''
    with open(output_path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(_CSV_HEADER)
        for site in stats.sites:
            writer.writerow(_site_csv_row(site))
        writer.writerow(_grand_total_csv_row(stats))
        writer.writerow([])
        writer.writerow(['Summary', 'Value'])
        writer.writerow(['Total Sites', stats.total_sites])
        writer.writerow(['Total EventIDs', stats.total_events])
        writer.writerow(['Total Validated DICOM Files', stats.total_files])
    _logger.info('Wrote %s', output_path)


def write_markdown(stats: ReportStats, output_path: str, title: str) -> None:
    '''Write a Markdown rendering of the summary table.'''
    lines: list[str] = [
        f'# {title}',
        '',
        '| Blinded SiteID | Total EventIDs | Missing Required Tags | Critical Errors/Corrupted Files | Potential identifiers in the header | Potential burned-in Identifiers in Pixels |',
        '| --- | ---: | ---: | ---: | ---: | ---: |',
    ]

    def _row(label: str, total: int, getter_count, getter_pct) -> str:
        cells = [
            label,
            str(total),
            _format_count_pct(getter_count('missing'), getter_pct('missing')),
            _format_count_pct(getter_count('error'), getter_pct('error')),
            _format_count_pct(getter_count('header'), getter_pct('header')),
            _format_count_pct(getter_count('burned'), getter_pct('burned')),
        ]
        return '| ' + ' | '.join(cells) + ' |'

    for site in stats.sites:
        lines.append(_row(site.site_id, site.total_events, site.affected_count, site.affected_pct))
    lines.append(_row('**Grand Total**', stats.total_events, stats.affected_count, stats.affected_pct))
    lines.extend([
        '',
        '## Summary',
        '',
        f'- **{stats.total_sites:,}** Total Sites',
        f'- **{stats.total_events:,}** Total EventIDs',
        f'- **{stats.total_files:,}** Total Validated DICOM Files',
        '',
        '## Methods',
        '',
        '- One row per site CSV under `sites/`.',
        '- **Total EventIDs** is the count of distinct `Event ID` values in that site CSV.',
        '- Columns for Missing Required Tags, Critical Errors/Corrupted Files, Potential identifiers in the header, and Potential burned-in Identifiers in Pixels count distinct Event IDs with at least one matching finding (`⚠️ Missing Required Tags`, `❌ Error`, `🙈 Possible PHI/PII in Header`, `🖼️ Possible Burned-in PHI/PII (Pixels)`). Displayed as `n (x.xx%)` of that site\'s Total EventIDs.',
        '- All `👮 Warning` findings are ignored and do not contribute to any percentage column.',
        '- **Total Validated DICOM Files** is the count of distinct files across all site CSVs, keyed as `Site ID / Event ID / File Path`.',
        '',
    ])
    with open(output_path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    _logger.info('Wrote %s', output_path)


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    '''Return (width, height) for text using textbbox.'''
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _wrap_header(text: str, max_width: int, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont) -> list[str]:
    '''Word-wrap a header cell into multiple lines that fit max_width.'''
    words = text.split()
    if not words:
        return ['']
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f'{current} {word}'
        width, _ = _text_size(draw, candidate, font)
        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def write_png(stats: ReportStats, output_path: str, title: str) -> None:
    '''Render a dc.png-style summary table image with side callouts.'''
    # Column definitions: (header label, width)
    columns = [
        ('Blinded SiteID', 180),
        ('Total EventIDs', 90),
        ('Missing Required Tags', 130),
        ('Critical Errors/Corrupted Files', 130),
        ('Potential identifiers in the header', 150),
        ('Potential burned-in Identifiers in Pixels', 160),
    ]

    title_font = _load_font(22, bold=True)
    header_font = _load_font(11, bold=True)
    cell_font = _load_font(12)
    cell_bold = _load_font(12, bold=True)
    callout_value_font = _load_font(20, bold=True)
    callout_label_font = _load_font(12)
    footnote_font = _load_font(10)

    # Colors matching the example image
    white = (255, 255, 255)
    black = (33, 37, 41)
    header_bg = (198, 214, 230)
    grand_bg = (198, 214, 230)
    zebra_bg = (248, 250, 252)
    header_col_bg = (198, 226, 245)  # column E highlight (matches dc.png)
    clean_row_bg = (210, 236, 210)  # light green for sites with no C–F findings
    grid = (160, 170, 180)
    callout_border = (180, 200, 220)
    callout_fill = (245, 250, 255)
    callout_value = (30, 90, 160)
    title_color = (20, 40, 70)

    padding = 24
    row_height = 28
    header_height = 56
    title_height = 40
    callout_width = 220
    callout_gap = 12
    footnote_height = 54
    table_width = sum(width for _, width in columns)
    header_col_index = 4  # Potential identifiers in the header

    n_rows = len(stats.sites) + 1  # sites + grand total
    table_height = header_height + n_rows * row_height
    callouts_height = 3 * 70 + 2 * callout_gap
    content_height = max(table_height, callouts_height)
    img_width = padding * 2 + table_width + 20 + callout_width
    img_height = padding + title_height + 8 + content_height + footnote_height + padding

    image = Image.new('RGB', (img_width, img_height), white)
    draw = ImageDraw.Draw(image)

    # Title
    draw.text((padding, padding), title, fill=title_color, font=title_font)

    table_left = padding
    table_top = padding + title_height + 8

    # Header background
    draw.rectangle(
        [table_left, table_top, table_left + table_width, table_top + header_height],
        fill=header_bg, outline=grid,
    )

    # Header text
    x = table_left
    for idx, (label, width) in enumerate(columns):
        cell_fill = header_col_bg if idx == header_col_index else header_bg
        draw.rectangle(
            [x, table_top, x + width, table_top + header_height],
            fill=cell_fill, outline=grid,
        )
        lines = _wrap_header(label, width - 8, draw, header_font)
        line_heights = [_text_size(draw, line, header_font)[1] for line in lines]
        block_height = sum(line_heights) + max(0, len(lines) - 1) * 2
        ty = table_top + (header_height - block_height) // 2
        for line, lh in zip(lines, line_heights):
            tw, _ = _text_size(draw, line, header_font)
            tx = x + (width - tw) // 2
            draw.text((tx, ty), line, fill=black, font=header_font)
            ty += lh + 2
        x += width

    def _cell_texts_for_site(site: SiteStats) -> list[str]:
        return [
            site.site_id,
            str(site.total_events),
            _format_count_pct(site.affected_count('missing'), site.affected_pct('missing')),
            _format_count_pct(site.affected_count('error'), site.affected_pct('error')),
            _format_count_pct(site.affected_count('header'), site.affected_pct('header')),
            _format_count_pct(site.affected_count('burned'), site.affected_pct('burned')),
        ]

    def _cell_texts_grand_total() -> list[str]:
        return [
            'Grand Total',
            str(stats.total_events),
            _format_count_pct(stats.affected_count('missing'), stats.affected_pct('missing')),
            _format_count_pct(stats.affected_count('error'), stats.affected_pct('error')),
            _format_count_pct(stats.affected_count('header'), stats.affected_pct('header')),
            _format_count_pct(stats.affected_count('burned'), stats.affected_pct('burned')),
        ]

    def _is_clean(site: SiteStats) -> bool:
        return all(site.affected_count(key) == 0 for key in _CATEGORY_KEYS)

    # Body rows: (texts, row_bg, is_bold, tint_header_column)
    rows: list[tuple[list[str], tuple[int, int, int], bool, bool]] = []
    for i, site in enumerate(stats.sites):
        if _is_clean(site):
            bg = clean_row_bg
            tint_header = False  # keep clean-row green intact
        else:
            bg = zebra_bg if i % 2 else white
            tint_header = True
        rows.append((_cell_texts_for_site(site), bg, False, tint_header))
    rows.append((_cell_texts_grand_total(), grand_bg, True, False))

    y = table_top + header_height
    for texts, bg, is_bold, tint_header in rows:
        draw.rectangle(
            [table_left, y, table_left + table_width, y + row_height],
            fill=bg, outline=grid,
        )
        x = table_left
        font = cell_bold if is_bold else cell_font
        for idx, ((_, width), text) in enumerate(zip(columns, texts)):
            if idx == header_col_index and tint_header:
                draw.rectangle(
                    [x + 1, y + 1, x + width - 1, y + row_height - 1],
                    fill=header_col_bg,
                )
            tw, th = _text_size(draw, text, font)
            if idx == 0:
                tx = x + 6
            else:
                tx = x + (width - tw) // 2
            ty = y + (row_height - th) // 2
            draw.text((tx, ty), text, fill=black, font=font)
            draw.line([(x, y), (x, y + row_height)], fill=grid)
            x += width
        draw.line([(table_left + table_width, y), (table_left + table_width, y + row_height)], fill=grid)
        y += row_height

    # Outer border
    draw.rectangle(
        [table_left, table_top, table_left + table_width, table_top + table_height],
        outline=grid, width=1,
    )

    # Side callouts
    callout_x = table_left + table_width + 20
    callout_y = table_top
    callouts = [
        (f'{stats.total_sites}', 'Total Sites'),
        (f'{stats.total_events:,}', 'Total EventIDs'),
        (f'{stats.total_files:,}', 'Total Validated DICOM Files'),
    ]
    for value, label in callouts:
        box = [callout_x, callout_y, callout_x + callout_width, callout_y + 70]
        draw.rounded_rectangle(box, radius=12, fill=callout_fill, outline=callout_border, width=2)
        vw, vh = _text_size(draw, value, callout_value_font)
        lw, _ = _text_size(draw, label, callout_label_font)
        draw.text(
            (callout_x + (callout_width - vw) // 2, callout_y + 12),
            value, fill=callout_value, font=callout_value_font,
        )
        draw.text(
            (callout_x + (callout_width - lw) // 2, callout_y + 12 + vh + 6),
            label, fill=black, font=callout_label_font,
        )
        callout_y += 70 + callout_gap

    # Footnote
    footnote = (
        'C–F: distinct EventIDs with ≥1 finding of that type ÷ Total EventIDs (👮 Warning ignored). '
        'DICOM files: distinct Site ID / Event ID / File Path across sites/ CSVs.'
    )
    fw = img_width - 2 * padding
    words = footnote.split()
    flines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f'{current} {word}'
        if _text_size(draw, candidate, footnote_font)[0] <= fw:
            current = candidate
        else:
            flines.append(current)
            current = word
    flines.append(current)
    fy = table_top + content_height + 16
    for line in flines:
        draw.text((padding, fy), line, fill=(90, 90, 90), font=footnote_font)
        fy += _text_size(draw, line, footnote_font)[1] + 2

    image.save(output_path, format='PNG')
    _logger.info('Wrote %s', output_path)


def write_pet_file_counts(stats: ReportStats) -> None:
    '''Write per-site distinct PET-profile file counts to stdout.'''
    for site in stats.sites:
        print(f'Site {site.site_id}: {site.pet_files} PET files', flush=True)


def generate_site_summary(report_folder: str, title: str = _DEFAULT_TITLE) -> ReportStats:
    '''Aggregate and write PNG, CSV, and Markdown into report_folder.'''
    stats = aggregate_report(report_folder)
    write_csv(stats, os.path.join(report_folder, _CSV_NAME))
    write_markdown(stats, os.path.join(report_folder, _MD_NAME), title=title)
    write_png(stats, os.path.join(report_folder, _PNG_NAME), title=title)
    write_pet_file_counts(stats)
    _logger.info(
        'Summary: %d sites, %d EventIDs, %s validated DICOM files',
        stats.total_sites, stats.total_events, f'{stats.total_files:,}',
    )
    return stats


def main() -> None:
    '''Entrypoint for summarize-site-reports.'''
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--title',
        default=_DEFAULT_TITLE,
        help='Title drawn on the PNG (and Markdown heading); defaults to "%(default)s"',
    )
    parser.add_argument(
        'report_folder',
        help='Report folder containing a sites/ subfolder of per-site CSV files '
             '(example: reports/Lung_Team_Project_2)',
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    generate_site_summary(args.report_folder, title=args.title)
    sys.exit(0)


if __name__ == '__main__':
    main()
