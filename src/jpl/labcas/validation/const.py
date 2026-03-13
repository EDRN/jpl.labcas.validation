# encoding: utf-8

'''🛂 EDRN DICOM Validation: constants.'''

IMAGE_SCORE       = 0.8  # Hard-coded score for image findings
PHI_PII_THRESHOLD = 0.8  # Default score ≥ to this means the file is probably not de-identified
PROCESS_TIMEOUT   = 30   # How many seconds to wait for a process to finish

# Files to ignore when scanning for DICOM files
IGNORED_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini', 'DICOMDIR', 'DICOMDIR.dcm', 'Image.dir', 'Series.dir', '_OLD_'}

# Folders whose contents we can skip completely
IGNORED_FOLDERS = {'thumbnails'}

# Minimum file size to be considered for validation, ~~15 KB~~
# @hoodriverheather says in a comment in EDRN/jpl.labcas.validation#31 that PET files show up too often
# as "file too small", so let's reduce it by half to 7.5 KB
MINIMUM_FILE_SIZE = int(7.5 * 1024)

# Minimum number of rows and columns for MR localizer files
# See EDRN/jpl.labcas.validation#31 for more details
MINIMUM_MR_LOC_ROWS = 96
MINIMUM_MR_LOC_COLUMNS = 96
