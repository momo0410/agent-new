declare global {
  interface Window {
    showNotification?: (message: string, type?: 'success' | 'error' | 'info' | 'warning') => void;
  }
}

export {};
