from typing import Any, Dict
THEMES = {
    "light": {
        "name": "浅色主题",
        "mode": "light",
        "colors": {
            "primary": "#1890ff",
            "background": "#ffffff",
            "surface": "#f5f5f5",
            "text": "#333333",
            "textSecondary": "#666666",
            "border": "#e0e0e0",
            "success": "#52c41a",
            "warning": "#faad14",
            "error": "#ff4d4f",
            "info": "#1890ff",
        },
    },
    "dark": {
        "name": "深色主题",
        "mode": "dark",
        "colors": {
            "primary": "#177ddc",
            "background": "#1f1f1f",
            "surface": "#2a2a2a",
            "text": "#e0e0e0",
            "textSecondary": "#a0a0a0",
            "border": "#404040",
            "success": "#49aa19",
            "warning": "#d89614",
            "error": "#d32029",
            "info": "#177ddc",
        },
    },
    "sakura": {
        "name": "樱花粉主题",
        "mode": "light",
        "colors": {
            "primary": "#e91e8c",
            "background": "#fff0f5",
            "surface": "#fce4ec",
            "text": "#4a1942",
            "textSecondary": "#880e4f",
            "border": "#f8bbd0",
            "success": "#4caf50",
            "warning": "#ff9800",
            "error": "#f44336",
            "info": "#e91e8c",
        },
    },
}
def get_theme_settings(current_theme: str = "light") -> Dict[str, Any]:
    return {
        "current_theme": current_theme,
        "available_themes": list(THEMES.keys()),
        "theme_config": THEMES.get(current_theme, THEMES["light"]),
    }
def get_all_themes() -> Dict[str, Dict[str, Any]]:
    return THEMES