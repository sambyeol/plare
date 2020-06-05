from setuptools import find_packages
from setuptools import setup

setup_params = dict(
  name='plare',
  version='1.0',
  description='Language description language, Lexer, and Parser for Python3',
  url='https://github.com/HenryLee97/plare',
  author='Henry Lee',
  author_email='gbvrcx@gmail.com',
  packages=find_packages(exclude=['tutorial']),
  setup_requires=[], 
  install_requires=[], 
  dependency_links=[],
)

if __name__ == '__main__':
  setup(**setup_params)
