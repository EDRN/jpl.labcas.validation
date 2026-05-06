# encoding: utf-8

'''🛂 EDRN DICOM Validation: constants.'''

IMAGE_SCORE       = 0.8  # Hard-coded score for image findings
PHI_PII_THRESHOLD = 0.8  # Default score ≥ to this means the file is probably not de-identified
PROCESS_TIMEOUT   = 30   # How many seconds to wait for a process to finish

# Files to ignore when scanning for DICOM files
IGNORED_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini', 'DICOMDIR', 'DICOMDIR.dcm', 'Image.dir', 'Series.dir', '_OLD_'}

# Folders whose contents we can skip completely
IGNORED_FOLDERS = {'thumbnails'}

# Minimum number of rows and columns for MR localizer files
# See EDRN/jpl.labcas.validation#31 for more details
#
# Ah but @hoodriverheather says in https://github.com/EDRN/jpl.labcas.validation/issues/31#issuecomment-4256524804
# That they should not be skipped so there's no need for these constants anymore.
#
# Why are they even called out in the spreadsheet?
MINIMUM_MR_LOC_ROWS = 96
MINIMUM_MR_LOC_COLUMNS = 96

# SOP Class UID prefixes for non-image DICOM files; these come right from the "SOP Class UID Routing"
# tab of the spreadsheet
NON_IMAGE_SOP_CLASS_UIDS = {
    '1.2.840.10008.5.1.4.1.1.88.67',
    '1.2.840.10008.5.1.4.1.1.11.1',
    '1.2.840.10008.5.1.4.1.1.88.11',
    '1.2.840.10008.5.1.4.1.1.88.22',
    '1.2.840.10008.5.1.4.1.1.88.59',
}
