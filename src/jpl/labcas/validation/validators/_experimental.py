# encoding: utf-8

'''🛂 EDRN DICOM Validation: experimental validators.

These validators are mostly for testing and development purposes.
'''

from .._classes import Validator, ValidationFinding
import pydicom


class ExperimentalModalityValidator(Validator):
    '''An experimental validator that always is upset at the "Modaity" tag even if it has a correct value.'''

    description = 'Experimental Modality (always fails) for tag (0008,0060)'
    tag = pydicom.tag.Tag((0x0008, 0x0060))

    def validate(self, ds: pydicom.Dataset) -> list[ValidationFinding]:
        return [ValidationFinding(
            file=ds.filename, value=ds.Modality, tag=self.tag,description='Modality is always UNACCEPTABLE for testing'
        )]


class ExperimentalManufacturerValidator(Validator):
    '''An experimental validator that is happy to accept the "Manufacturer" tag even if it's is missing.'''

    description = 'Experimental Manufacturer (always passes) for tag (0008,0070)'
    tag = pydicom.tag.Tag((0x0008, 0x0070))

    def validate(self, ds: pydicom.Dataset) -> list[ValidationFinding]:
        return []  # No findings means we're happy

