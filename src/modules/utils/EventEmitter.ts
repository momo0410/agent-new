export class EventEmitter<T> {
  private _listeners: Array<(data: T) => void> = [];

  addListener(listener: (data: T) => void): void {
    this._listeners.push(listener);
  }

  removeListener(listener: (data: T) => void): void {
    const index = this._listeners.indexOf(listener);
    if (index > -1) {
      this._listeners.splice(index, 1);
    }
  }

  protected emit(data: T): void {
    this._listeners.forEach(listener => {
      try {
        listener(data);
      } catch (error) {
        console.error('监听器执行失败:', error);
      }
    });
  }
}
