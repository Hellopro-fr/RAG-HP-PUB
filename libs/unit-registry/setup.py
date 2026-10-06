from setuptools import find_packages, setup

setup(
    name="unit-registry",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=["pint==0.24.4"],
)
