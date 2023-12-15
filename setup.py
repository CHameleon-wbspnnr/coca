#!/usr/bin/env python
from setuptools import setup

setup(name='JetFactory',
      version='0.1',
      description='',
      author='Azkali Manad',
      author_email='a.ffcc7@gmail.com',
      url='https://gitlab.com/switchroot/gnu-linux/jet-factory/',
      install_requires=[
        "patool",
        "filesplit",
        "clint",
        "sh",
        "requests",
        "PyInquirer",
        "envbash"
      ]
)
