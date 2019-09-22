from setuptools import setup, find_packages
import os

# Get the long description from the README file
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='kaldi-active-grammar',
    version='0.8.0',
    description='Kaldi speech recognition with grammars that can be set active/inactive dynamically at decode-time',  # Optional
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/daanzu/kaldi-active-grammar',
    author='David Zurow',
    author_email='daanzu@gmail.com',
    license='AGPL-3.0, with exceptions',
    classifiers=[  # Optional
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3',
         'Programming Language :: Python :: 3',
         'Programming Language :: Python :: 3.4',
         'Programming Language :: Python :: 3.5',
         'Programming Language :: Python :: 3.6',
         'Programming Language :: Python :: 3.7',
    ],
    keywords='kaldi speech recognition grammar',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    python_requires='>3',
    install_requires=[
        'cffi ~= 1.12',
        'numpy ~= 1.16',
        'ush ~= 3.1',
        'requests >= 2'
    ],
    package_data={
        'kaldi_active_grammar': ['exec/*/*']
    },
)
