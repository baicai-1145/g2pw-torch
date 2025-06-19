from setuptools import setup, find_packages

setup(
    name='g2pw_torch',
    version='0.1.0',
    description='A PyTorch-based G2P (Grapheme-to-Phoneme) converter for Chinese, modified to support direct .pth model loading.',
    long_description=open('README.md', encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    author='baicai1145',
    author_email='your.email@example.com',  # Please change this
    url='https://github.com/baicai1145/g2pw-torch',
    packages=find_packages(),
    install_requires=[
        'torch',
        'transformers',
        'numpy',
        'tqdm',
        'requests',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Topic :: Text Processing :: Linguistic',
    ],
    python_requires='>=3.8',
)
