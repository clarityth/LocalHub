const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  })

  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // 서버가 JSON이 아닌 오류를 내려도 화면에는 최소한의 상태 코드를 보여준다.
    }
    throw new Error(message)
  }

  return response.status === 204 ? null : response.json()
}

export const api = {
  listLocations(params = {}) {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(key, value)
    })
    return request(`/locations${query.toString() ? `?${query}` : ''}`)
  },
  getLocation(contentid) {
    return request(`/locations/${contentid}`)
  },
  listPosts(params = {}) {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(key, value)
    })
    return request(`/posts${query.toString() ? `?${query}` : ''}`)
  },
  getPost(id) {
    return request(`/posts/${id}`)
  },
  createPost(payload) {
    return request('/posts', { method: 'POST', body: JSON.stringify(payload) })
  },
  updatePost(id, payload) {
    return request(`/posts/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
  },
  deletePost(id, password) {
    return request(`/posts/${id}`, { method: 'DELETE', body: JSON.stringify({ password }) })
  },
  likePost(id) {
    return request(`/posts/${id}/like`, { method: 'POST' })
  },
  async chat(payload, onChunk, onMetadata) {
    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6).trim();
          if (dataStr === '[DONE]') return;
          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);
            if (data.type === 'metadata') {
              if (onMetadata) onMetadata(data);
            } else if (data.type === 'content') {
              if (onChunk) onChunk(data.text);
            }
          } catch (e) {
            console.error('SSE JSON parse error:', e, dataStr);
          }
        }
      }
    }
  }
}
