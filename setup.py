from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8") if (this_directory / "README.md").exists() else ""

setup(
    name="veloroute",
    version="1.0.0",
    description="Enterprise Universal AI Gateway, High-Availability LLM Routing & Token-Saviour Optimization Engine",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mrgusux/veloroute",
    author="Mr. Gusu",
    author_email="monirmdmunna123@gmail.com",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "veloroute": [
            "ui/templates/*.html",
            "ui/templates/pages/*.html",
            "ui/templates/**/*",
        ],
    },
    install_requires=[
        "fastapi>=0.115.0",
        "uvicorn>=0.30.0",
        "httpx>=0.27.0",
        "pydantic>=2.0.0",
        "jinja2>=3.1.0",
        "python-dotenv>=1.0.0",
        "python-multipart>=0.0.9",
        "sqlalchemy>=2.0.0",
        "aiosqlite>=0.20.0",
        "greenlet>=3.0.0",
    ],
    extras_require={
        "all": [
            "aiomysql>=0.2",
            "asyncpg>=0.30",
            "motor>=3.3",
            "redis>=5.0",
        ],
        "dev": [
            "playwright>=1.40",
        ],
    },
    entry_points={
        "console_scripts": [
            "veloroute=veloroute.cli:main",
        ],
    },
    python_requires=">=3.11",
)
