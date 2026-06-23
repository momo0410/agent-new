export type EncodingType = 'url' | 'base64' | 'hex' | 'html' | 'unicode' | 'jwt';

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

const bytesToBase64 = (bytes: Uint8Array): string => {
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
};

const base64ToBytes = (value: string): Uint8Array => {
  const normalized = value.replace(/\s+/g, '').replace(/-/g, '+').replace(/_/g, '/');
  if (!normalized) {
    return new Uint8Array();
  }

  const padding = normalized.length % 4;
  const padded = padding === 0 ? normalized : normalized + '='.repeat(4 - padding);
  const binary = atob(padded);

  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
};

const encodeBase64 = (value: string): string => bytesToBase64(textEncoder.encode(value));

const decodeBase64 = (value: string): string => textDecoder.decode(base64ToBytes(value));

const encodeHex = (value: string): string => Array.from(textEncoder.encode(value))
  .map((byte) => byte.toString(16).padStart(2, '0'))
  .join('');

const decodeHex = (value: string): string => {
  const normalized = value.replace(/\s+/g, '');

  if (!normalized) {
    return '';
  }

  if (normalized.length % 2 !== 0) {
    throw new Error('Hex 字符串长度必须为偶数');
  }

  if (!/^[0-9a-fA-F]+$/.test(normalized)) {
    throw new Error('Hex 字符串只能包含 0-9 和 A-F');
  }

  const bytes = normalized.match(/.{2}/g) ?? [];
  return textDecoder.decode(new Uint8Array(bytes.map((byte) => parseInt(byte, 16))));
};

const encodeHtml = (value: string): string => value
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#x27;');

const decodeHtml = (value: string): string => value
  .replace(/&#x([0-9a-fA-F]+);/g, (_, hex: string) => String.fromCodePoint(parseInt(hex, 16)))
  .replace(/&#([0-9]+);/g, (_, dec: string) => String.fromCodePoint(parseInt(dec, 10)))
  .replace(/&(amp|lt|gt|quot|apos);/g, (match, entity: string) => {
    switch (entity) {
      case 'amp':
        return '&';
      case 'lt':
        return '<';
      case 'gt':
        return '>';
      case 'quot':
        return '"';
      case 'apos':
        return "'";
      default:
        return match;
    }
  });

const encodeUnicode = (value: string): string => Array.from(value)
  .map((char) => {
    const codePoint = char.codePointAt(0);

    if (codePoint === undefined) {
      return '';
    }

    if (codePoint <= 0xFFFF) {
      return `\\u${codePoint.toString(16).padStart(4, '0')}`;
    }

    const normalized = codePoint - 0x10000;
    const highSurrogate = 0xD800 + (normalized >> 10);
    const lowSurrogate = 0xDC00 + (normalized & 0x3FF);

    return `\\u${highSurrogate.toString(16).padStart(4, '0')}\\u${lowSurrogate.toString(16).padStart(4, '0')}`;
  })
  .join('');

const decodeUnicode = (value: string): string => value
  .replace(/\\u\{([0-9a-fA-F]+)\}/g, (_, hex: string) => String.fromCodePoint(parseInt(hex, 16)))
  .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex: string) => String.fromCharCode(parseInt(hex, 16)));

const encodeJwtSegment = (value: unknown): string => encodeBase64(JSON.stringify(value))
  .replace(/\+/g, '-')
  .replace(/\//g, '_')
  .replace(/=+$/g, '');

const decodeJwtSegment = (segment: string, label: string): unknown => {
  try {
    return JSON.parse(decodeBase64(segment));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`JWT ${label} 解析失败: ${message}`);
  }
};

export const encodeByType = (type: EncodingType, value: string): string => {
  switch (type) {
    case 'url':
      return encodeURIComponent(value);
    case 'base64':
      return encodeBase64(value);
    case 'hex':
      return encodeHex(value);
    case 'html':
      return encodeHtml(value);
    case 'unicode':
      return encodeUnicode(value);
    case 'jwt': {
      const normalized = value.trim();

      if (!normalized) {
        return '';
      }

      let payload: unknown;

      try {
        payload = JSON.parse(normalized);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        throw new Error(`JWT payload 必须是有效的 JSON: ${message}`);
      }

      const header = { alg: 'none', typ: 'JWT' };
      return `${encodeJwtSegment(header)}.${encodeJwtSegment(payload)}.`;
    }
  }
};

export const decodeByType = (type: EncodingType, value: string): string => {
  switch (type) {
    case 'url':
      return decodeURIComponent(value);
    case 'base64':
      return decodeBase64(value);
    case 'hex':
      return decodeHex(value);
    case 'html':
      return decodeHtml(value);
    case 'unicode':
      return decodeUnicode(value);
    case 'jwt': {
      const parts = value.split('.');

      if (parts.length !== 3) {
        throw new Error('无效的 JWT Token 格式');
      }

      const header = decodeJwtSegment(parts[0], 'header');
      const payload = decodeJwtSegment(parts[1], 'payload');

      return JSON.stringify({ header, payload, signature: parts[2] }, null, 2);
    }
  }
};
