from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent.absolute()
long_description = Path(this_directory, 'README.md').read_text(encoding='utf-8')

setup(
    name='streamcapture',
    description='Capture output streams such as sys.stdout and sys.stderr.',
    version='1.1.1',
    packages=find_packages(),
    install_requires=['setuptools', 'pdoc3>=0.7'],
    python_requires='>=3',
    author='Sébastien Loisel',
    author_email='sloisel@gmail.com',
    zip_safe=False,
    url='https://github.com/sloisel/streamcapture',
    project_urls={
        'Documentation': 'https://htmlpreview.github.io/?https://github.com/sloisel/streamcapture/blob/master/streamcapture.html',
        'Source': 'https://github.com/sloisel/streamcapture',
    },
    license='MIT',
    long_description=long_description,
    long_description_content_type='text/markdown',
)
