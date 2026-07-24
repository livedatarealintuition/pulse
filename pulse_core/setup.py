from setuptools import setup, find_packages

setup(
    name="pulse_core",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "yfinance>=0.2.36",
        "requests>=2.31.0",
    ],
    python_requires=">=3.9",
)
