"""
RX65N Virtual Emulator Setup
"""

from setuptools import setup, find_packages

setup(
    name='rx-emulator',
    version='0.1.0',
    description='RX65N Microcontroller Virtual Emulator',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='RX Emulator Team',
    python_requires='>=3.8',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'rx-emulator=rx_emulator.__main__:main',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Topic :: Software Development :: Embedded Systems',
        'Topic :: System :: Emulators',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
