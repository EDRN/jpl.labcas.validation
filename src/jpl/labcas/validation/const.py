# encoding: utf-8

'''🛂 EDRN DICOM Validation: constants.'''

IMAGE_SCORE       = 0.8  # Hard-coded score for image findings
PHI_PII_THRESHOLD = 0.8  # Default score ≥ to this means the file is probably not de-identified
PROCESS_TIMEOUT   = 30   # How many seconds to wait for a process to finish

# Files to ignore when scanning for DICOM files
IGNORED_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini', 'DICOMDIR', 'DICOMDIR.dcm', 'Image.dir', 'Series.dir', '_OLD_'}

# Folders whose contents we can skip completely
IGNORED_FOLDERS = {'thumbnails'}

# Minimum file size to be considered for validation, 15 KB
MINIMUM_FILE_SIZE = 15 * 1024
