# encoding: utf-8

'''🛂 EDRN DICOM Validation: simple scoring PHI/PII recognizer.'''

from .._classes import PHI_PII_Recognizer, Finding, HeaderFinding, ImageFinding, ErrorFinding
from ..const import IMAGE_SCORE
from collections import Counter
from PIL import Image
from pydicom import datadict
from typing import Iterable
import pydicom, logging, argparse, re, pytesseract, math

# Avoid problematic DICOM files so we can still grab as many of the tags and values as we can
pydicom.config.convert_wrong_length_to_UN = True

_logger = logging.getLogger(__name__)


class SimpleScoring_PHI_PII_Recognizer(PHI_PII_Recognizer):
    '''A simple scoring PHI/PII recognizer.'''

    description = 'Simple scoring PHI/PII recognizer uses patterns in certain well-known tags and in pixels to detect PHI/PII'
    _max_normalized_string = 5000  # How many characters to limit when textifying DICOM metadata tag values

    # Tags that are *genuinely risky by semantics* (person identifiers & clinician names)
    _strict_tags = {
        # Patient/person identifiers
        (0x0010, 0x0010),  # PatientName
        (0x0010, 0x0030),  # PatientBirthDate
        (0x0010, 0x1000),  # OtherPatientIDs
        (0x0010, 0x1001),  # OtherPatientNames
        (0x0010, 0x4000),  # PatientComments

        # Clinician/operator name fields
        (0x0008, 0x0090),  # ReferringPhysicianName
        (0x0008, 0x1048),  # PhysiciansOfRecord
        (0x0008, 0x1050),  # PerformingPhysicianName
        (0x0008, 0x1060),  # NameOfPhysiciansReadingStudy
        (0x0008, 0x1070),  # OperatorsName
    }

    # These tend to have less identifiable information
    _medium_tags = {
        (0x0010, 0x0020),  # PatientID
        (0x0010, 0x2160),  # EthnicGroup
        (0x0010, 0x2180),  # Occupation
        (0x0010, 0x1040),  # PatientAddress
        (0x0010, 0x0035),  # PatientBirthName
        (0x0010, 0x1060),  # PatientMotherBirthName
        (0x0018, 0x1000),  # DeviceSerialNumber
    }

    # Text but low-risk and contextual, not identifiers; we don't auto-flag these
    _contextual_low_risk_tags = {
        (0x0008, 0x0080),  # InstitutionName
        (0x0008, 0x0081),  # InstitutionAddress
        (0x0008, 0x1030),  # StudyDescription
        (0x0008, 0x103E),  # SeriesDescription
        (0x0008, 0x2111),  # DerivationDescription
        (0x0020, 0x4000),  # ImageComments
    }

    # Common regexes for de-identified text values
    _anonymized_patterns = [
        re.compile(r'^(ANON|ANONYMOUS|REDACTED|REMOVED|UNKNOWN|N/A|null|NA)$', re.IGNORECASE),
        re.compile(r'^PATIENT\^TEST$', re.IGNORECASE),
        re.compile(r'^(TEST|DEMO|SYNTHETIC|DUMMY)$', re.IGNORECASE),
    ]

    # Imaging jargon to filter out (to reduce name_like noise)
    _non_person_hints = re.compile(
        r'\b(AXIAL|CORONAL|SAGITTAL|T1|T2|FLAIR|AX|COR|SAG|SE|GRE|B\-VALUE|ADC)\b', re.IGNORECASE
    )
    
    # VRs (value representations) that commonly carry free text
    _free_text_VRs = {'AE', 'AS', 'CS', 'LO', 'LT', 'PN', 'SH', 'ST', 'UC', 'UT', 'UR'}

    # DICOM Person Name fields in structured PN form (e.g., DOE^JOHN, SMITH^ANNE^Q)
    _pn_structured = re.compile(r"^[A-Z0-9]{2,}(?:[-'][A-Z0-9]+)*(\^[A-Z0-9]{1,}(?:[-'][A-Z0-9]+)*)+$")

    # Regexes by name → compiled pattern
    _patterns = {
        'EMAIL': re.compile(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', re.IGNORECASE),
        'PHONE': re.compile(r'\b(?:\+\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b'),
        'SSN': re.compile(r'\b\d{3}[- ]?\d{2}[- ]?\d{4}\b'),
        'MRN_like': re.compile(r'\b(?:MRN|Med(?:ical)?\s*Record)\s*[:#]?\s*[A-Z0-9\-]{3,}\b', re.IGNORECASE),
        'DOB_like': re.compile(r'(?:DOB|Birth\s*Date)\s*[:#]?\s*(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})', re.IGNORECASE),
        # Conservative 'Firstname Lastname' structure (kept for non-PN text where allowed)
        'NAME_like': re.compile(r"\b([A-Z][a-z]+(?:[-'][A-Z][a-z]+)?\s+[A-Z][a-z]+)\b"),
        'URL': re.compile(r'\bhttps?://[^\s]+', re.IGNORECASE),
    }

    # We don't treat institition names as PHI/PII; flip this if necessary
    _suppress_institution_names = True

    # Vendor tags that are safe to include
    _vendor_safe_tags = {'Manufacturer', 'ManufacturerModelName', 'DeviceManufacturerName', 'SoftwareVersions'}

    # Allowed vendors
    _vendor_allow_list = {
        'SIEMENS',
        'SIEMENS MEDICAL SYSTEMS',
        'GE',
        'GE HEALTHCARE',
        'GE MEDICAL SYSTEMS',
        'PHILIPS',
        'PHILIPS MEDICAL SYSTEMS',
        'CANON MEDICAL',
        'AGFA',
        'FUJIFILM',
        'VARIAN',
        'HITACHI',
    }        

    # Only allow name-like patterns on these explicit person-named keywords
    _name_like_allowed_tags = {
        'PatientName',
        'ReferringPhysicianName',
        'PhysiciansOfRecord',
        'PerformingPhysicianName',
        'NameOfPhysiciansReadingStudy',
        'OperatorsName',
    }

    def __init__(self, args: argparse.Namespace):
        '''Initialize the recognizer with the given arguments.'''
        self.score = args.score

    def _extract_frames(self, ds: pydicom.Dataset, max_frames: int = 4) -> list:
        '''Extract up to `max_frames` frames from the given DICOM dataset.'''
        frames = []
        # The `pixel_array` is a `@property` which even if we just do `hasattr` can cause
        # a whole bunch of things to happen—and raise exceptions!
        if not hasattr(ds, 'pixel_array'): return frames

        try:
            # And then grab it:
            arr = ds.pixel_array  # This can raise a whole heapload of exceptions, so we just catch Exception below

            # Multi-frame DICOM have `ndim` (number dimensions)
            if getattr(arr, 'ndim', 0) == 3:
                # (frames, rows cols) or (rows, cols, channels)
                if arr.shape[0] > 8 and arr.shape[0] >= max_frames:
                    # There could be hundreds of frames, so we get evenly spaced ones with a step size
                    step = max(1, arr.shape[0] // max_frames)  ## step size with larger of 1 and floor division
                    frame_indexes = list(range(0, arr.shape[0], step))[:max_frames]
                    for i in frame_indexes:
                        if arr.shape[-1] in (3, 4):  # RGB(A)
                            frames.append(Image.fromarray(arr))
                            break
                        frames.append(Image.fromarray(arr[i]))
                else:
                    if arr.shape[-1] in (3, 4):  # RGB(A)
                        frames.append(Image.fromarray(arr))
                    else:
                        for i in range(min(max_frames, arr.shape[0])):
                            frames.append(Image.fromarray(arr[i]))
            elif getattr(arr, 'ndim', 0) == 2:
                # Single grayscale image
                frames.append(Image.fromarray(arr))
            else:
                # Some unexpected like a 1D array or a 4D hyperstack, so just _try_ to render it
                frames.append(Image.fromarray(arr))
        except Exception:
            _logger.exception('💥 Unexpected (but ignored) exception extracting frames from %s', ds.filename)

        # Normalize to 8-bit so we can do OCR
        normalized = []
        for f in frames:
            try:
                if f.mode not in ('L', 'RGB'):
                    normalized.append(f.convert('L'))  # L = lumincance (grayscale)
                else:
                    normalized.append(f)
            except Exception:
                continue

        # Whew
        return normalized[:max_frames]

    def _recognize_characters(self, frame: Image.Image) -> tuple[str, list[tuple[int, int, int, int]]]:
        '''Recognize characters in the given frame using OCR.'''
        try:
            data = pytesseract.image_to_data(frame, output_type=pytesseract.Output.DICT)
            n = len(data.get('text', []))
            boxes, texts = [], []
            for i in range(n):
                txt = (data.get('text')[i] or '').strip()
                if not txt: continue
                texts.append(txt)
                x, y, w, h = data.get('left')[i], data.get('top')[i], data.get('width')[i], data.get('height')[i]
                boxes.append((x, y, w, h))
            return ''.join(texts), boxes
        except Exception:
            try:
                t = pytesseract.image_to_string(frame)
                return t, []
            except Exception:
                return '', []   

    def _recognize_pixels(self, ds: pydicom.Dataset) -> list[Finding]:
        '''Recognize PHI/PII in the pixels of the given DICOM dataset.'''
        findings: list[Finding] = []
        try:
            frames = self._extract_frames(ds)
        except Exception as ex:
            _logger.exception('💥 Unexpected exception extracting frames from %s', ds.filename)
            findings.append(ErrorFinding(
                file=ds.filename, value='💥 Unexpected exception extracting pixel frames', error_message=str(ex)
            ))
        if not frames: return findings
        for idx, frame in enumerate(frames):
            text, boxes = self._recognize_characters(frame)        
            if not text: continue
            for key, rx in self._patterns.items():
                for m in rx.finditer(text):
                    excerpt = text[max(0, m.start() - 24):m.end() + 24]  # Grab 24 characters of context on each side
                    finding = ImageFinding(
                        file=ds.filename, value=self._displayable_str(excerpt), pattern=key,
                        score=IMAGE_SCORE, index=idx
                    )
                    findings.append(finding)
        return findings

    def _normalize_text_for_match(self, s: str) -> str:
        '''Normalize text for matching against vendor phrases in the allow list.
        
        This is a simple normalization that removes whitespace and punctuation,
        and converts to uppercase.
        '''
        return re.sub(r'\s+', ' ', re.sub(r'[^A-Za-z0-9]+', ' ', s or '')).strip().upper()

    def _displayable_str(self, v, max_length: int = 80) -> str:
        '''Return a string version of `v` and limit it to `max_length` characters.'''
        if v is None: return ''
        s = str(v)
        return s[:max_length] + '…' if len(s) > max_length else s

    def _iter_over_dicom_elements(
        self, ds: pydicom.Dataset, path_prefix: str = ''
    ) -> Iterable[tuple[str, str, str, pydicom.tag.Tag]]:
        '''Iterate over all elements in the given DICOM dataset.
        
        This yields tuples of (path, value, value representation, tag).
        '''
        for elem in ds.iterall():
            t = pydicom.tag.Tag(elem.tag)
            vr = elem.VR if hasattr(elem, 'VR') else None
            name = elem.keyword or elem.name or f'{t.group:04x}{t.element:04x}'
            path = f'{path_prefix}.{name}' if path_prefix else name
            if vr == 'SQ':
                # Recurse into sequences
                for idx, item in enumerate(elem.value or []):
                    sub_prefix = f'{path}[{idx}]'
                    yield from self._iter_over_dicom_elements(item, sub_prefix)
            else:
                yield path, elem.value, vr, t

    def _normalize_text(self, s: str) -> str:
        '''Normalizes a string by removing null bytes, stripping, and truncating.'''
        s = (s or '').replace('\x00', '').strip()
        return s[:self._max_normalized_string] if len(s) > self._max_normalized_string else s

    def _textify(self, obj) -> list[str]:
        '''Recursively extract human text from common DICOM value shapes.'''
        out: list[str] = []

        def _recurse(x):
            if x is None: return
            # Lazy imports, tolerate version differences
            try: from pydicom.multival import MultiValue
            except Exception: MultiValue = tuple()  # type: ignore

            if isinstance(x, (bytes, bytearray)):
                try: s = x.decode(errors='ignore')
                except Exception: return
                s = self._normalize_text(s)
                if s: out.append(s)
                return

            if isinstance(x, str):
                s = self._normalize_text(x)
                if s: out.append(s)
                return

            if isinstance(x, (list, tuple, set, MultiValue)):
                for item in x: _recurse(item)
                return

            # --- Scalar / object fallback ---
            # pydicom PN class names vary by version; don’t rely on exact class.
            # If stringified value looks like text (letters or caret), keep it.
            try: s = self._normalize_text(str(x))
            except Exception: return

            # Keep only if it contains textual signal (avoid plain numbers & empty reprs)
            if s and re.search(r'[A-Za-z@^]', s): out.append(s)
            # else: ignore numbers/UIDs/etc.

        _recurse(obj)

        # Deduplicate while preserving order
        seen, uniq = set(), []
        for s in out:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        return uniq

    def _high_entropy(self, s: str) -> bool:
        '''Return True if the string has high entropy, False otherwise.
        
        Uses Shannon entropy to detect random-looking strings (IDs, tokens, etc.)
        that are likely not human-readable names.
        '''
        if not s or len(s) < 3: return False
        
        # Calculate Shannon entropy
        char_counts = Counter(s)
        
        entropy = 0.0
        length = len(s)
        for count in char_counts.values():
            p = count / length
            entropy -= p * math.log2(p)
        
        # Normalize by maximum possible entropy (log2 of unique chars)
        max_entropy = math.log2(len(char_counts))
        if max_entropy == 0: return False
        
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
        
        # High entropy threshold: > 0.85 and at least 4 unique characters
        return normalized_entropy > 0.85 and len(char_counts) >= 4


    def _score(self, tag: pydicom.tag.Tag, vr: str | None, value: any, matched_key: str | None) -> float:
        '''Heuristic confidence (0..1) that a finding could be PHI/PII.

        Uses:
        - tag semantics (self._strict_tags vs contextual)
        - free-text VRs (light)
        - which detector fired (weighted)
        - value-level hints (dummy placeholders; modality jargon)
        '''
        text = str(value or '').strip()

        for rx in self._anonymized_patterns:
            if rx.match(text):
                return 0.1

        score = 0.1
        tg = (tag.group, tag.element)

        # Tag semantics
        if tg in self._strict_tags:
            score += 0.6
        elif tg in self._medium_tags:
            score += 0.2  # was 0.6 before; now medium unless more evidence
        elif tg in self._contextual_low_risk_tags:
            score += 0.0  # super explicit that these don't add risk 😁

        # Free-text VRs (value representations)
        if vr in self._free_text_VRs:
            score += 0.15

        # Pattern evidence
        if matched_key:
            if matched_key in {'EMAIL', 'PHONE', 'SSN'}:
                score += 0.5
            elif matched_key in {'MRN_like', 'DOB_like'}:
                score += 0.35
            elif matched_key == 'NAME_like':
                score += 0.2
                if self._non_person_hints.search(text):
                    score -= 0.15
            elif matched_key == 'PN_structured':
                score += 0.30

        # Added by ChatGPT: PN fields that *don’t* look like names → dampen
        if vr == 'PN' and not (self._pn_structured.match(text) or self._patterns['NAME_like'].search(text)):
            score -= 0.35   # pulls 0.85 → ~0.50

        # (Optional) If you want to go further for obvious pseudonyms
        # if vr == "PN" and PSEUDOID_LIKE.match(text):
        #     score -= 0.15

        return max(0.0, min(1.0, score))  # Clamp!


    def _recognize_tags(self, ds: pydicom.Dataset) -> list[Finding]:
        '''Recognize PHI/PII in the tags of the given DICOM dataset.'''
        # Gather all candidate strings from the dataset
        findings: list[Finding] = []
        for path, value, vr, t in self._iter_over_dicom_elements(ds):
            # Skip binary VRs (OB, OW, OF, OD, OL, OV, UN) because they contain raw data, not text
            if vr in ('OB', 'OW', 'OF', 'OD', 'OL', 'OV', 'UN'): continue

            # Gather all the text candidates from the value
            candidates: list[str] = self._textify(value)

            # Skip institution names if we're suppressing them
            if self._suppress_institution_names and (t.group, t.element) == (0x0008, 0x0080): continue

            # Auto-flag truly risky tags and only when we have real text
            if (t.group, t.element) in self._strict_tags:
                tag_keyword = datadict.keyword_for_tag(t)
                for c in candidates:
                    c = c.strip()
                    if 'anonymized' in c.lower():
                        continue
                    elif self._high_entropy(c):
                        # Skip high-entropy strings (likely IDs, tokens, hashes)
                        continue
                    elif c:
                        score = self._score(t, vr, c, None)
                        finding = HeaderFinding(
                            file=ds.filename, value=self._displayable_str(c), score=score, tag=t,
                            description=f'Strict high-risk tag "{tag_keyword}" may need closer look with score {score}'
                        )
                        findings.append(finding)

            # Pattern-based detection (emails, phone numbers, SSNs, DOBs, person names, etc.)
            elem = ds.get_item(t)
            # RawDataElement objects don't have a keyword attribute, so use getattr with fallback to datadict
            tag_keyword = getattr(elem, 'keyword', None) if elem is not None else None
            if tag_keyword is None:
                tag_keyword = datadict.keyword_for_tag(t) or ''
            else:
                tag_keyword = tag_keyword or ''
            vendor_context = tag_keyword in self._vendor_safe_tags

            # Allow name-like patterns where the keyword says it's a name or when value-representation
            # (VR) is explicitly person name (PN)
            allow_name_like_here = (tag_keyword in self._name_like_allowed_tags) or (vr == 'PN')

            for c in candidates:
                if not c.strip(): continue

                # Special case: DICOM person name (PN) structured name detection (only when allowed
                # as a name field)
                if allow_name_like_here and self._pn_structured.match(c):
                    finding = HeaderFinding(
                        file=ds.filename, value=self._displayable_str(c), score=self._score(t, vr, c, 'PN_structured'), tag=t,
                        description=f'Structured name detection «{c}»'
                    )
                    findings.append(finding)
                    # Continue here to avoid double-counting with the NAME_like pattern
                    continue
                
                # Normal pattern-based detection
                for key, rx in self._patterns.items():
                    # Suppress NAME_like in non-person fields entirely
                    if key == 'NAME_like' and not allow_name_like_here: continue

                    # If in vendor fields, avoid vendor/manufacturer phrases
                    if key == 'NAME_like' and vendor_context:
                        norm = self._normalize_text_for_match(c)
                        if norm in self._vendor_allow_list: continue

                    # Try to match against the current pattern
                    if rx.search(c):
                        finding = HeaderFinding(
                            file=ds.filename, value=self._displayable_str(c), score=self._score(t, vr, c, key), tag=t,
                            description=f'Using pattern {key}'
                        )
                        findings.append(finding)

        return findings

    def recognize(self, ds: pydicom.Dataset) -> list[Finding]:
        findings = self._recognize_tags(ds) + self._recognize_pixels(ds)
        return findings


