
import os
import sys

from setuptools import setup, find_packages

setup(

    name='ecp5_pcie',
    version = "0.0.1",
    # TODO license='',
    url='https://github.com/ECP5-PCIe/ECP5-PCIe',
    description='PCIe interface for the ECP5 FPGA in amaranth',

    # Imports / exports / requirements.
    platforms='any',
    packages=['ecp5_pcie'],
    include_package_data=True,
    python_requires="~=3.7",
    install_requires=['amaranth'],
    setup_requires=['setuptools']
)