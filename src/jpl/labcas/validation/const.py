# encoding: utf-8

'''🛂 EDRN DICOM Validation: constants.'''

DEFAULT_PROTOCOL  = 430  # The default protocol ID, 430 is Prostate_MRI
IMAGE_SCORE       = 0.8  # Hard-coded score for image findings
PHI_PII_THRESHOLD = 0.8  # Default score ≥ to this means the file is probably not de-identified
PROCESS_TIMEOUT   = 30   # How many seconds to wait for a process to finish

# Files to ignore when scanning for DICOM files
IGNORED_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini', 'DICOMDIR', 'Image.dir', 'Series.dir'}
