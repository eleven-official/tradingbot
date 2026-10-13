"""Loki Desktop Application Package"""

# Make imports work properly
try:
    from loki.desktop.enhanced_app import LokiEnhancedApp, main
    __all__ = ['LokiEnhancedApp', 'main']
except ImportError:
    try:
        from loki.desktop.app import LokiDesktopApp, main
        __all__ = ['LokiDesktopApp', 'main']
    except ImportError:
        __all__ = []
