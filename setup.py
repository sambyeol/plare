from setuptools import find_packages
from setuptools import setup

setup_params = dict(
  name='PyPar',
  version='1.0',
  description='Language description language, Lexer, and Parser for Python3',
  url='https://github.com/HenryLee97/PyPar',
  author='Henry Lee',
  author_email='gbvrcx@gmail.com',
  packages=find_packages(exclude=['example',]),
  setup_requires=[], 
  install_requires=[], 
  dependency_links=[],
)

if __name__ == '__main__':
  setup(**setup_params)
