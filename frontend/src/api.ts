export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch('/api' + path, { ...options, headers: { ...headers, ...options.headers } });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    const detail = error?.detail;
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join('；') : `请求失败 (${response.status})`);
  }
  return response.json();
}
