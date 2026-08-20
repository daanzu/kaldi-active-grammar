"""Package version fallback for imports directly from a source checkout.

Wheel builds replace the copy of this module in the build directory with the
exact generated distribution version; the checked-in file is never rewritten.
"""

__version_base__ = '4.0.0'
__version__ = __version_base__ + '.dev0'
__version_generated__ = False
