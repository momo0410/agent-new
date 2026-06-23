from typing import Any, Dict, Optional
class WindowManager:
    def __init__(self):
        self._windows: Dict[str, Dict[str, Any]] = {}
    def create_window(
        self, label: str, title: str, url: str, width: float = 900, height: float = 600
    ) -> Dict[str, Any]:
        window_info = {
            "label": label,
            "title": title,
            "url": url,
            "width": width,
            "height": height,
        }
        self._windows[label] = window_info
        return window_info
    def get_window(self, label: str) -> Optional[Dict[str, Any]]:
        return self._windows.get(label)
    def close_window(self, label: str) -> bool:
        if label in self._windows:
            del self._windows[label]
            return True
        return False
    def list_windows(self) -> Dict[str, Dict[str, Any]]:
        return self._windows.copy()