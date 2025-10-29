# encoding: utf-8

'''🛂 EDRN DICOM Validation: argument parsing.'''


from . import VERSION
import logging


def add_logging_argparse_options(parser):
    '''Add logging options to the given `parser`.'''
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '-d',
        '--debug',
        action='store_const',
        const=logging.DEBUG,
        default=logging.INFO,
        dest='loglevel',
        help='Log copious debugging messages suitable for developers',
    )
    group.add_argument(
        '-q',
        '--quiet',
        action='store_const',
        const=logging.WARNING,
        dest='loglevel',
        help="Don't log anything except warnings and critically-important messages",
    )


def add_standard_argparse_options(parser):
    '''Add the regular set of expected options (logging, version).'''

    # First, add the `--version` option
    parser.add_argument('--version', action='version', version=VERSION)

    # Now logging
    add_logging_argparse_options(parser)
