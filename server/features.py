"""Demo exposure switches; absent or any value other than 1 is off."""
import os


def extra_modes():
    return os.environ.get('ENABLE_EXTRA_MODES') == '1'


def shopping():
    return os.environ.get('SHOPPING') == '1'
