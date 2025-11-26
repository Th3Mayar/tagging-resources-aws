from setuptools import setup, find_packages

setup(
    name="tagging-resources-aws",
    version="0.1.6",
    description="Tag propagator and AWS resource tagging toolkit",
    author="Jose Francisco Henriquez",
    packages=find_packages(),
    install_requires=[
        "boto3>=1.34.0",
    ],
    entry_points={
        "console_scripts": [
            "tag-propagate=tagging_resources_aws.tag_propagate:main",
        ],
    },
    data_files=[
        ('/usr/share/bash-completion/completions', ['bash_completion/tagging']),
    ],
)