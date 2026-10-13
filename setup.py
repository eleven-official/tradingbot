"""
Loki Trading Platform - Enterprise Setup Configuration
Production-ready algorithmic trading system
"""
from setuptools import setup, find_packages
import os

# Read version from version file
def get_version():
    version_file = os.path.join(os.path.dirname(__file__), 'loki', 'version.py')
    with open(version_file, 'r') as f:
        exec(f.read())
        return locals()['__version__']

# Read long description from README
def get_long_description():
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    with open(readme_path, 'r', encoding='utf-8') as f:
        return f.read()

setup(
    name='loki-trading-platform',
    version=get_version(),
    author='Loki Trading Systems',
    author_email='support@lokitrading.ai',
    description='Enterprise-grade AI-powered algorithmic trading platform',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    url='https://github.com/lokitrading/loki',
    packages=find_packages(exclude=['tests', 'tests.*', 'docs', 'examples']),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Financial and Insurance Industry',
        'Topic :: Office/Business :: Financial :: Investment',
        'License :: Other/Proprietary License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Operating System :: OS Independent',
        'Environment :: Web Environment',
        'Framework :: FastAPI',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
    ],
    python_requires='>=3.10',
    install_requires=[
        # Core dependencies
        'numpy>=1.24.0',
        'pandas>=2.0.0',
        'scipy>=1.10.0',
        
        # Data and visualization
        'matplotlib>=3.7.0',
        'plotly>=5.14.0',
        'seaborn>=0.12.0',
        
        # Machine Learning
        'scikit-learn>=1.3.0',
        'tensorflow>=2.13.0',
        'torch>=2.0.0',
        'xgboost>=2.0.0',
        'lightgbm>=4.0.0',
        
        # Trading and Market Data
        'alpaca-py>=0.10.0',
        'yfinance>=0.2.28',
        'ccxt>=4.0.0',
        
        # Web Framework
        'fastapi>=0.104.0',
        'uvicorn[standard]>=0.24.0',
        'websockets>=12.0',
        'pydantic>=2.4.0',
        'pydantic-settings>=2.0.0',
        
        # Database
        'sqlalchemy>=2.0.0',
        'alembic>=1.12.0',
        'psycopg2-binary>=2.9.9',
        'redis>=5.0.0',
        
        # Task Queue
        'celery>=5.3.0',
        'kombu>=5.3.0',
        
        # Authentication & Security
        'python-jose[cryptography]>=3.3.0',
        'passlib[bcrypt]>=1.7.4',
        'python-multipart>=0.0.6',
        
        # Monitoring & Logging
        'prometheus-client>=0.18.0',
        'structlog>=23.2.0',
        'sentry-sdk>=1.38.0',
        
        # Configuration
        'pyyaml>=6.0',
        'python-dotenv>=1.0.0',
        
        # HTTP & API
        'httpx>=0.25.0',
        'aiohttp>=3.9.0',
        'requests>=2.31.0',
        
        # Data validation
        'marshmallow>=3.20.0',
        'jsonschema>=4.19.0',
        
        # Utilities
        'pytz>=2023.3',
        'python-dateutil>=2.8.2',
        'click>=8.1.7',
        'rich>=13.6.0',
        'tqdm>=4.66.0',
    ],
    extras_require={
        'desktop': [
            'PyQt6>=6.6.0',
            'PyQt6-WebEngine>=6.6.0',
            'pyqtgraph>=0.13.3',
        ],
        'web': [
            'nextjs-python>=0.1.0',  # For Next.js integration
            'gunicorn>=21.2.0',
        ],
        'dev': [
            'pytest>=7.4.0',
            'pytest-asyncio>=0.21.0',
            'pytest-cov>=4.1.0',
            'pytest-mock>=3.12.0',
            'black>=23.11.0',
            'flake8>=6.1.0',
            'mypy>=1.7.0',
            'isort>=5.12.0',
            'pre-commit>=3.5.0',
        ],
        'docs': [
            'sphinx>=7.2.0',
            'sphinx-rtd-theme>=1.3.0',
            'sphinx-autodoc-typehints>=1.25.0',
            'myst-parser>=2.0.0',
        ],
        'all': [
            'PyQt6>=6.6.0',
            'gunicorn>=21.2.0',
            'pytest>=7.4.0',
            'sphinx>=7.2.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'loki=loki.cli:main',
            'loki-server=loki.api.server:main',
            'loki-worker=loki.tasks.worker:main',
            'loki-desktop=loki.desktop.app:main',
            'loki-migrate=loki.database.migrate:main',
        ],
    },
    include_package_data=True,
    package_data={
        'loki': [
            'static/**/*',
            'templates/**/*',
            'config/*.yaml',
            'migrations/**/*',
        ],
    },
    zip_safe=False,
    keywords='trading algorithmic-trading machine-learning finance quantitative-finance',
    project_urls={
        'Documentation': 'https://docs.lokitrading.ai',
        'Source': 'https://github.com/lokitrading/loki',
        'Bug Reports': 'https://github.com/lokitrading/loki/issues',
        'Changelog': 'https://github.com/lokitrading/loki/blob/main/CHANGELOG.md',
    },
)
