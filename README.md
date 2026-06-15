# 🛂 EDRN DICOM Validation

This is the [DICOM](https://www.dicomstandard.org) validation tool for the [Laboratory Catalog and Archive Service](https://edrn-labcas.jpl.nasa.gov/) (LabCAS). It ensures that DICOM files:

- **Contain little-to-no PHI/PII** — Scans both DICOM headers and pixel data for protected health information (PHI) and personally identifiable information (PII)
- **Adhere to EDRN requirements** — Validates DICOM tags against the [EDRN core validation spreadsheet](https://docs.google.com/spreadsheets/d/1MPSEOMTVnT-eVL8AXLXVebuBOqNDSxrz_cqAV1az_N4/edit?gid=1392488545#gid=1392488545)

This tool was originally developed in response to [EDRN/EDRN-metadata#160](https://github.com/EDRN/EDRN-metadata/issues/160).


## 🎯 Features

This program has features described in the following subsections.


### 🔍 PHI/PII Detection

- **Header-based detection**: Scans DICOM metadata tags for identifiers including:
    - Patient names, birth dates, addresses
    - Physician and operator names
    - Email addresses, phone numbers, SSNs
    - Medical record numbers (MRNs)
- **Pixel-based detection**: Uses OCR (via [Tesseract](https://tesseract-ocr.github.io)) to detect text embedded in DICOM images
- **Multiple recognizers**: Choose between different PHI/PII detection algorithms:
    - `simple-scoring` (default): Pattern-based detection with configurable scoring
    - `accepting`: Accepts all files (usually used for testing only)
    - `rejecting`: Rejects all files (used for testing only)


### ✅ DICOM Tag Validation

Validates over 40 DICOM tags against EDRN requirements including:

- **Study/Series/Image Identification**: UIDs, instance numbers, SOP class
- **Acquisition Modality and Equipment**: Modality codes, manufacturer info, device details
- **Temporal Data**: Dates and times in proper format
- **Image Data**: Dimensions, pixel data, display parameters
- **MR-specific**: Spacing between slices validation


### 📊 Reporting

Generates CSV reports organized by:

- Site ID
- Event ID  
- File name
- Finding type and severity score


## 📦 Installation

Details on installing this software follows in this section.


### ⚙️ Prerequisites

Requires Python 3.12 or higher and Tesseract OCR for pixel-based PHI/PII detection.


#### 🔤 Tesseract

[Tesseract](https://github.com/tesseract-ocr/tesseract) provides optical character recgonition features for this program and must be installed separately.

**macOS**:
```bash
brew install tesseract
```

**Linux** (Ubuntu/Debian):
```bash
sudo apt-get install tesseract-ocr
```

**Windows**:
Download from https://github.com/UB-Mannheim/tesseract/wiki


### 📥 Install the Package

It's best to set up a Python virtual environment and use `pip` to install it into that environment:

    pip install jpl.labcas.validation

Or install from source:
```bash
git clone https://github.com/EDRN/jpl.labcas.validation.git
cd jpl.labcas.validation
pip install --editable .
```

## 🚀 Usage

The following describes how to use this program.


### 📀 Preparing DICOM Files

DICOM files should be arranged in a way that mirrors the expectations of LabCAS, which arranges files into folders in a specific hierarchy, described below:

```


### 💻 Basic Usage

The easiest way to run this is:

    validate-dicom-files <directory>/.../<collection-folder>

the `<directory>` should eventually contain the following directory hierarchy:

    <directory>
        … (sub-directories)
        collection-folder (such as Prostate_MRI)
            event-ID-folder (such as 1234567)
            … (sub-folders)
                DICOM file 1
                DICOM file 2
                …


### ⚡ Command-Line Options

Use `--help` to get more details, but summarizing:

- `-s, --score <value>`: Maximum PHI/PII score threshold (0.0-1.0, default: 0.8)
- `-c, --concurrency <num>`: Number of concurrent processes (default: CPU count)
- `-r, --recognizer <name>`: PHI/PII recognizer to use:
  - `simple-scoring` (default): Pattern-based detection
  - `accepting`: Accept all files
  - `rejecting`: Reject all files
- `-o, --output <dir>`: Output directory for CSV reports (default: current directory)
- `--log-file <file>`: Write detailed logs to a file while keeping the progress bar readable
- `-d, --debug`: Debug logging
- `-q, --quiet`: Quiet logging

Validation shows a progress bar on stderr. Without `--log-file`, normal log messages are routed through tqdm so they do not garble the progress display. With `--log-file`, detailed logs go to the file and only errors and critical messages are also shown on stderr.

### 📝 Examples

Validate a directory with default settings:

    validate-dicom-files /path/to/dicom/files

Use a different PHI/PII threshold (lower = less strict):

    validate-dicom-files --score 0.5 /path/to/dicom/files

Generate a custom report filename:

    validate-dicom-files --output validation_results.md /path/to/dicom/files

Use a specific number of workers:

    validate-dicom-files --concurrency 4 /path/to/dicom/files

In general, use a `--concurrency` equal to at least the number of CPU cores available. Some recommend using twice that number.


## 📖 Understanding the Report

The tool generates a Markdown report with findings organized hierarchically:

1. **By Site ID**: Grouped by blinded site identifier
2. **By Event ID**: Grouped by 7-digit event ID
3. **By File**: Individual DICOM files within each event
4. **By Finding**: Each finding includes:
   - **Score**: Severity from 0.0 (low) to 1.0 (high)
   - **Kind**: Type of finding:
     - 🙈 Header: PHI/PII found in DICOM metadata
     - 🖼️ Pixels: PHI/PII found in image data via OCR
     - ⚠️ Validation: Tag compliance issue
     - ❌ Error: File reading or processing error
   - **Details**: Specific information about the finding

Only findings with scores above the threshold are included in the report.


## 🏗️ Architecture

The validation framework is modular and extensible:

- **PHI/PII Recognizers**: Plug-in system for different detection algorithms
- **Validators**: Individual validators for each DICOM tag requirement
- **Findings**: Structured representation of all issues discovered


## 🧪 Development Status

Development Status: Pre-Alpha

CT requirements may be added in the future, pending completion of the [spreadsheet's CT tab](https://docs.google.com/spreadsheets/d/1oQB0EoeajxFagSrIzF_8hOIc6hbC9MiMvhbYLfr6vPQ/edit?pli=1&gid=1779958583#gid=1779958583).


## 📄 License

Apache 2.0 - See LICENSE.md for details


## 🤝 Contributing

Issues and pull requests welcome on GitHub: https://github.com/EDRN/jpl.labcas.validation/issues. See also the EDRN [Code of Conduct](https://github.com/EDRN/.github/blob/main/CODE_OF_CONDUCT.md) and [Contributors' Guide](https://github.com/EDRN/.github/blob/main/CONTRIBUTING.md).


## 👤 Authors

- Sean Kelly `@nutjob4life`


## ©️ Copyright

Copyright © 2025 California Institute of Technology. U.S. Government sponsorship acknowledged.

