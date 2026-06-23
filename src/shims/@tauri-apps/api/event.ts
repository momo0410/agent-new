/**
 * @tauri-apps/api/event shim
 * 在纯 Web/Python 模式下提供最小事件能力。
 */

export type UnlistenFn = () => void;

export interface TauriEvent<T = unknown> {
  event: string;
  id: number;
  payload: T;
}

export type EventCallback<T = unknown> = (event: TauriEvent<T>) => void;

const THEME_STORAGE_KEY = 'LERT-theme';
const CUSTOM_EVENT_PREFIX = '__tauri_event__:';
let eventId = 0;

function getCustomEventName(event: string): string {
  return `${CUSTOM_EVENT_PREFIX}${event}`;
}

function nextEventId(): number {
  eventId += 1;
  return eventId;
}

function buildEvent<T>(event: string, payload: T): TauriEvent<T> {
  return {
    event,
    id: nextEventId(),
    payload,
  };
}

export async function listen<T = unknown>(event: string, handler: EventCallback<T>): Promise<UnlistenFn> {
  const customEventName = getCustomEventName(event);

  const onCustomEvent = (rawEvent: Event) => {
    const payload = (rawEvent as CustomEvent<T>).detail;
    handler(buildEvent(event, payload));
  };

  const onStorageEvent = (storageEvent: StorageEvent) => {
    if (event !== 'theme-changed') return;
    if (storageEvent.key !== THEME_STORAGE_KEY) return;
    if (!storageEvent.newValue) return;
    handler(buildEvent(event, storageEvent.newValue as T));
  };

  window.addEventListener(customEventName, onCustomEvent as EventListener);
  window.addEventListener('storage', onStorageEvent);

  return () => {
    window.removeEventListener(customEventName, onCustomEvent as EventListener);
    window.removeEventListener('storage', onStorageEvent);
  };
}

export async function once<T = unknown>(event: string, handler: EventCallback<T>): Promise<UnlistenFn> {
  let unlisten: UnlistenFn = () => {};
  unlisten = await listen<T>(event, (payloadEvent) => {
    unlisten();
    handler(payloadEvent);
  });
  return unlisten;
}

export async function emit<T = unknown>(event: string, payload?: T): Promise<void> {
  const customEventName = getCustomEventName(event);
  window.dispatchEvent(new CustomEvent(customEventName, { detail: payload }));
}
