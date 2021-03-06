# -*- coding: utf-8 -*-

# DO NOT EDIT THIS FILE!
# This file has been autogenerated by dephell <3
# https://github.com/dephell/dephell

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import os.path

readme = ''
here = os.path.abspath(os.path.dirname(__file__))
readme_path = os.path.join(here, 'README.rst')
if os.path.exists(readme_path):
    with open(readme_path, 'rb') as stream:
        readme = stream.read().decode('utf8')

setup(
    long_description=readme,
    name='liquidpy',
    version='0.5.0',
    description='A port of liquid template engine for python',
    python_requires='==3.*,>=3.6.0',
    project_urls={
        "homepage": "https://github.com/pwwang/liquidpy",
        "repository": "https://github.com/pwwang/liquidpy"
    },
    author='pwwang',
    author_email='pwwang@pwwang.com',
    license='MIT',
    packages=['liquid'],
    package_dir={"": "."},
    package_data={"liquid": ["*.bak"]},
    install_requires=['attr-property', 'attrs==19.*,>=19.3.0', 'diot'],
    extras_require={"dev": ["pytest", "pytest-cov"]},
)
