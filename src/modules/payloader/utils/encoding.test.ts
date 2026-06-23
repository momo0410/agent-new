import { describe, expect, it } from 'vitest';
import { decodeByType, encodeByType } from './encoding';

const toBase64Url = (value: string): string => encodeByType('base64', value)
  .replace(/\+/g, '-')
  .replace(/\//g, '_')
  .replace(/=+$/g, '');

describe('encoding utilities', () => {
  it('round-trips utf-8 content with base64', () => {
    const input = '你好，payload 😀';
    const encoded = encodeByType('base64', input);

    expect(decodeByType('base64', encoded)).toBe(input);
  });

  it('encodes JWT payloads as unsigned base64url tokens', () => {
    const token = encodeByType('jwt', JSON.stringify({ sub: '1234567890', name: 'Alice', role: 'admin' }));
    const parts = token.split('.');

    expect(parts).toHaveLength(3);
    expect(parts[2]).toBe('');

    const decoded = JSON.parse(decodeByType('jwt', token)) as {
      header: { alg: string; typ: string };
      payload: { sub: string; name: string; role: string };
      signature: string;
    };

    expect(decoded.header.alg).toBe('none');
    expect(decoded.header.typ).toBe('JWT');
    expect(decoded.payload.name).toBe('Alice');
    expect(decoded.payload.role).toBe('admin');
    expect(decoded.signature).toBe('');
  });

  it('decodes JWT payloads with base64url and utf-8 content', () => {
    const token = [
      toBase64Url(JSON.stringify({ alg: 'HS256', typ: 'JWT' })),
      toBase64Url(JSON.stringify({ name: '李子', role: 'admin', emoji: '😀' })),
      'signature_part',
    ].join('.');

    const decoded = JSON.parse(decodeByType('jwt', token)) as {
      header: { alg: string; typ: string };
      payload: { name: string; role: string; emoji: string };
      signature: string;
    };

    expect(decoded.header.alg).toBe('HS256');
    expect(decoded.payload.name).toBe('李子');
    expect(decoded.payload.emoji).toBe('😀');
    expect(decoded.signature).toBe('signature_part');
  });

  it('encodes unicode surrogate pairs completely', () => {
    expect(encodeByType('unicode', '😀')).toBe('\\ud83d\\ude00');
    expect(decodeByType('unicode', '\\ud83d\\ude00')).toBe('😀');
  });

  it('accepts spaced hex input and rejects invalid hex', () => {
    expect(decodeByType('hex', 'e4 bd a0 e5 a5 bd')).toBe('你好');
    expect(() => decodeByType('hex', 'abc')).toThrow('Hex 字符串长度必须为偶数');
    expect(() => decodeByType('hex', 'zz')).toThrow('Hex 字符串只能包含 0-9 和 A-F');
  });

  it('rejects invalid JSON when encoding JWT', () => {
    expect(() => encodeByType('jwt', '{invalid json}')).toThrow('JWT payload 必须是有效的 JSON');
  });
});
