"""A setuptools based setup module.

Basic usage::

    python setup.py bdist_wheel

Set ``KALDIAG_BUILD_SKIP_NATIVE=1`` to skip the native build when the required
libraries have already been placed in the package.

See:
https://packaging.python.org/guides/distributing-packages-using-setuptools/
https://github.com/pypa/sampleproject

Distribution policy: build platform-specific wheels only. Source distributions
(sdists) are intentionally unsupported because this package must bundle its
matching native Kaldi library.
"""

# Always prefer setuptools over distutils
from setuptools import find_packages
from setuptools.command.build_py import build_py as setuptools_build_py
import os
import platform
import re
import sys

# Optionally skip native code build (expecting libraries to be manually/externally placed correctly prior) by using standard setuptools; otherwise build native code with scikit-build
if os.environ.get('KALDIAG_BUILD_SKIP_NATIVE') or os.environ.get('KALDIAG_SETUP_RAW'):
    from setuptools import setup
    build_py_base = setuptools_build_py
else:
    from skbuild import setup
    from skbuild.command.build_py import build_py as build_py_base

import site
site.ENABLE_USER_SITE = bool("--user" in sys.argv[1:])  # Fix pip bug breaking editable install to user directory: https://github.com/pypa/pip/issues/7953


# Force wheel to be platform-specific (needed due to manually-loaded native libraries)
# https://stackoverflow.com/questions/45150304/how-to-force-a-python-wheel-to-be-platform-specific-when-building-it
# https://github.com/Yelp/dumb-init/blob/48db0c0d0ecb4598d1a6400710445b85d67616bf/setup.py#L11-L27
# https://github.com/google/or-tools/issues/616#issuecomment-371480314
if True:
    from wheel.bdist_wheel import bdist_wheel as bdist_wheel
    class bdist_wheel_impure(bdist_wheel):

        def finalize_options(self):
            super().finalize_options()
            # Mark us as not a pure python package: we contain platform-specific native libraries, even though no CPython extensions
            self.root_is_pure = False

        def get_tag(self):
            python, abi, plat = super().get_tag()
            # Mark us as python-version-agnostic (py3), and python-ABI-agnostic (none), since we contain no CPython extensions
            python, abi = 'py3', 'none'
            # For MacOS, prevent mistakenly marking as universal2 wheel (since we compile our native libraries as either x86_64 or arm64, not both)
            if plat.startswith("macosx_") and plat.endswith("_universal2"):
                want = "x86_64" if platform.machine() == "x86_64" else "arm64"
                plat = re.sub(r"_universal2$", f"_{want}", plat)
            return python, abi, plat

    from setuptools.command.install import install
    class install_platlib(install):
        def finalize_options(self):
            super().finalize_options()
            self.install_lib = self.install_platlib


here = os.path.abspath(os.path.dirname(__file__))

# Keep version calculation importable without importing the package, which loads
# the native library as part of normal package initialization.
sys.path.insert(0, os.path.join(here, 'building'))
from versioning import read_base_version, resolve_build_version  # noqa: E402

version_base = read_base_version(here)
version = resolve_build_version(here)


def write_version_module(version_path):
    with open(version_path, 'w') as version_file:
        version_file.write(
            '"""Generated package version; do not edit."""\n\n'
            "__version_base__ = %r\n"
            "__version__ = %r\n"
            "__version_generated__ = True\n" % (version_base, version))


class build_py_with_version(build_py_base):
    """Write the resolved version into the build tree, never the checkout."""

    def run(self):
        super().run()
        version_path = os.path.join(
            self.build_lib, 'kaldi_active_grammar', '_version.py')
        write_version_module(version_path)


# Set branch for Kaldi source repository (maybe we should use commits instead?)
if not os.environ.get('KALDI_BRANCH'):
    os.environ['KALDI_BRANCH'] = ('kag-v' + version) if ('dev' not in version) else 'origin/master'

# Get the long description from the README file
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()


# Arguments marked as "Required" below must be included for upload to PyPI.
# Fields marked as "Optional" may be commented out.

setup(
    cmdclass={
        'bdist_wheel': bdist_wheel_impure,
        'install': install_platlib,
        'build_py': build_py_with_version,
    },

    # This is the name of your project. The first time you publish this
    # package, this name will be registered for you. It will determine how
    # users can install this project, e.g.:
    #
    # $ pip install sampleproject
    #
    # And where it will live on PyPI: https://pypi.org/project/sampleproject/
    #
    # There are some restrictions on what makes a valid project name
    # specification here:
    # https://packaging.python.org/specifications/core-metadata/#name
    name='kaldi-active-grammar',  # Required

    # Versions should comply with PEP 440:
    # https://www.python.org/dev/peps/pep-0440/
    #
    # For a discussion on single-sourcing the version across setup.py and the
    # project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    # version='0.2.0',  # Required
    # version=open('VERSION').read().strip(),
    version=version,

    # This is a one-line description or tagline of what your project does. This
    # corresponds to the "Summary" metadata field:
    # https://packaging.python.org/specifications/core-metadata/#summary
    description='Kaldi speech recognition with grammars that can be set active/inactive dynamically at decode-time',  # Optional

    # This is an optional longer description of your project that represents
    # the body of text which users will see when they visit PyPI.
    #
    # Often, this is the same as your README, so you can just read it in from
    # that file directly (as we have already done above)
    #
    # This field corresponds to the "Description" metadata field:
    # https://packaging.python.org/specifications/core-metadata/#description-optional
    long_description=long_description,  # Optional

    # Denotes that our long_description is in Markdown; valid values are
    # text/plain, text/x-rst, and text/markdown
    #
    # Optional if long_description is written in reStructuredText (rst) but
    # required for plain-text or Markdown; if unspecified, "applications should
    # attempt to render [the long_description] as text/x-rst; charset=UTF-8 and
    # fall back to text/plain if it is not valid rst" (see link below)
    #
    # This field corresponds to the "Description-Content-Type" metadata field:
    # https://packaging.python.org/specifications/core-metadata/#description-content-type-optional
    long_description_content_type='text/markdown',  # Optional (see note above)

    # This should be a valid link to your project's main homepage.
    #
    # This field corresponds to the "Home-Page" metadata field:
    # https://packaging.python.org/specifications/core-metadata/#home-page-optional
    url='https://github.com/daanzu/kaldi-active-grammar',  # Optional

    # This should be your name or the name of the organization which owns the
    # project.
    author='David Zurow',  # Optional

    # This should be a valid email address corresponding to the author listed
    # above.
    author_email='daanzu@gmail.com',  # Optional

    license='AGPL-3.0-or-later',

    # Classifiers help users find your project by categorizing it.
    #
    # For a list of valid classifiers, see https://pypi.org/classifiers/
    classifiers=[  # Optional
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 5 - Production/Stable',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        # 'Topic :: Software Development :: Build Tools',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        # These classifiers are *not* checked by 'pip install'. See instead
        # 'python_requires' below.
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Programming Language :: Python :: Implementation :: CPython',
    ],

    # This field adds keywords for your project which will appear on the
    # project page. What does your project relate to?
    #
    # Note that this is a string of words separated by whitespace, not a list.
    keywords='kaldi speech recognition grammar dragonfly',  # Optional

    # You can just specify package directories manually here if your project is
    # simple. Or you can use find_packages().
    #
    # Alternatively, if you just want to distribute a single Python file, use
    # the `py_modules` argument instead as follows, which will expect a file
    # called `my_module.py` to exist:
    #
    #   py_modules=["my_module"],
    #
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),  # Required

    # Specify which Python versions you support. In contrast to the
    # 'Programming Language' classifiers above, 'pip install' will check this
    # and refuse to install the project if the version does not match. If you
    # do not support Python 2, you can simplify this to '>=3.5' or similar, see
    # https://packaging.python.org/guides/distributing-packages-using-setuptools/#python-requires
    python_requires='>=3.6, <4',  # NOTE: Allowing earlier unsupported versions, even if not tested, unless we know they break

    # This field lists other packages that your project depends on to run.
    # Any package you put here will be installed by pip when your project is
    # installed, so they must be valid existing projects.
    #
    # For an analysis of "install_requires" vs pip's requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=[
        'cffi >= 1.12',
        'numpy >= 1.16, != 1.19.4',
        'ush >= 3.1',
        'six',
        'futures; python_version == "2.7"',
    ],  # Optional

    # List additional groups of dependencies here (e.g. development
    # dependencies). Users will be able to install these using the "extras"
    # syntax, for example:
    #
    #   $ pip install sampleproject[dev]
    #
    # Similar to `install_requires` above, these must be valid existing
    # projects.
    extras_require={  # Optional
        'g2p_en': ['g2p_en >= 2.1.0'],
        'online': ['requests >= 2.18'],
        # 'dev': ['check-manifest'],
        # "test": [
        #     # See requirements-test.txt
        # ]
    },

    # package_dir={
    #     'kaldi_active_grammar': 'package'
    # },

    # If there are data files included in your packages that need to be
    # installed, specify them here.
    #
    # These entries are assembled into platform-specific wheels. Source
    # distributions are intentionally unsupported.
    package_data={  # Optional
        'kaldi_active_grammar': ['exec/*/*', 'exec/*/*/*'],
        '': ['LICENSE.txt'],
    },

    # Although 'package_data' is the preferred approach, in some case you may
    # need to place data files outside of your packages. See:
    # http://docs.python.org/3.4/distutils/setupscript.html#installing-additional-files
    #
    # In this case, 'data_file' will be installed into '<sys.prefix>/my_data'
    # data_files=[('my_data', ['data/data_file'])],  # Optional
    # data_files=[('my_data', ['exec/windows/dragonfly.dll'])],  # Optional
    # data_files=[('', ['LICENSE.txt'])],

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # `pip` to create the appropriate form of executable for the target
    # platform.
    #
    # For example, the following would provide a command called `sample` which
    # executes the function `main` from this package when invoked:
    # entry_points={  # Optional
    #     'console_scripts': [
    #         'sample=sample:main',
    #     ],
    # },

    # List additional URLs that are relevant to your project as a dict.
    #
    # This field corresponds to the "Project-URL" metadata fields:
    # https://packaging.python.org/specifications/core-metadata/#project-url-multiple-use
    #
    # Examples listed include a pattern for specifying where the package tracks
    # issues, where the source is hosted, where to say thanks to the package
    # maintainers, and where to support the project financially. The key is
    # what's used to render the link text on PyPI.
    project_urls={  # Optional
        'Bug Reports': 'https://github.com/daanzu/kaldi-active-grammar/issues',
        'Funding': 'https://github.com/sponsors/daanzu',
        # 'Say Thanks!': 'http://saythanks.io/to/example',
        'Source': 'https://github.com/daanzu/kaldi-active-grammar/',
    },
)
