<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import L from 'leaflet'
import { Bot, Heart, MapPin, MessageSquareText, Search, Send, Trash2, X, ChevronRight } from 'lucide-vue-next'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { api } from './api'

const categories = [
  { id: '', label: '전체' },
  { id: 12, label: '관광지' },
  { id: 14, label: '문화시설' },
  { id: 15, label: '축제' },
  { id: 25, label: '여행코스' },
  { id: 28, label: '레포츠' },
  { id: 32, label: '숙박' },
  { id: 38, label: '쇼핑' },
  { id: 39, label: '음식점' }
]

const activeTab = ref('places')
const typeId = ref('')
const searchText = ref('')
const locations = ref([])
const selectedLocation = ref(null)
const nearbyPlaces = ref([])
const posts = ref([])
const selectedPost = ref(null)
const postSearchText = ref('')
const postSearchType = ref('both')
const postSortBy = ref('latest')
const deletePassword = ref('')
const chatInput = ref('')
const chatMessages = ref([
  { role: 'assistant', content: '안녕하세요! 대전/충청권 여행 안내를 도와드리는 LocalHub 챗봇입니다. 원하시는 여행지나 코스를 물어보세요!' }
])
const loading = ref(false)
const error = ref('')
const isChatOpen = ref(false)
const isWritingPost = ref(false)

const postForm = ref({
  title: '',
  place: '',
  category: '여행 후기',
  content: '',
  password: '',
  contentid: ''
})

const showPlaceSuggestions = ref(false)
const placeSuggestions = computed(() => {
  if (!postForm.value.place || postForm.value.place.length < 1) return []
  const query = postForm.value.place.toLowerCase()
  return locations.value.filter(loc => loc.title.toLowerCase().includes(query)).slice(0, 5)
})

function selectPlaceSuggestion(loc) {
  postForm.value.place = loc.title
  postForm.value.contentid = loc.contentid
  showPlaceSuggestions.value = false
}

function hidePlaceSuggestions() {
  setTimeout(() => { showPlaceSuggestions.value = false }, 150)
}

let map
let markers = []

const shownLocations = computed(() => locations.value.slice(0, 150))

onMounted(async () => {
  await Promise.all([loadLocations(), loadPosts()])
  initMap()
})

async function loadLocations() {
  error.value = ''
  try {
    locations.value = await api.listLocations({
      contenttypeid: typeId.value,
      q: searchText.value,
      limit: typeId.value ? 700 : 1500
    })
    if (!selectedLocation.value && locations.value.length) {
      await openLocation(locations.value[0], false)
    }
    renderMarkers()
  } catch (err) {
    error.value = err.message
  }
}

async function openLocation(location, pan = true) {
  selectedLocation.value = await api.getLocation(location.contentid)
  postForm.value.place = selectedLocation.value.title
  postForm.value.contentid = selectedLocation.value.contentid
  nearbyPlaces.value = selectedLocation.value.nearby_places || []
  if (map && pan) map.setView([selectedLocation.value.mapy, selectedLocation.value.mapx], 14)
}

function initMap() {
  if (map) return
  map = L.map('map', { zoomControl: false }).setView([36.3504, 127.3845], 11)
  L.control.zoom({ position: 'bottomright' }).addTo(map)

  const ro = new ResizeObserver(() => {
    if (map) map.invalidateSize()
  })
  ro.observe(document.getElementById('map'))

  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map)
  renderMarkers()
}

function renderMarkers() {
  if (!map) return
  markers.forEach((marker) => marker.remove())
  markers = shownLocations.value.map((location) => {
    const marker = L.circleMarker([location.mapy, location.mapx], {
      radius: selectedLocation.value?.contentid === location.contentid ? 8 : 5,
      color: colorFor(location.contenttypeid),
      fillColor: colorFor(location.contenttypeid),
      fillOpacity: 0.82,
      weight: 2
    })
    marker.bindTooltip(location.title)
    marker.on('click', () => openLocation(location))
    marker.addTo(map)
    return marker
  })
}

function colorFor(id) {
  return {
    12: '#0ea5e9',
    14: '#8b5cf6',
    15: '#f43f5e',
    25: '#3b82f6',
    28: '#10b981',
    32: '#f59e0b',
    38: '#f97316',
    39: '#ec4899'
  }[id] || '#64748b'
}

async function loadPosts() {
  const params = {}
  if (postSearchText.value) params.q = postSearchText.value
  if (postSearchType.value) params.search_type = postSearchType.value
  if (postSortBy.value) params.sort_by = postSortBy.value
  
  posts.value = await api.listPosts(params)
}

const editingPostId = ref(null)

async function openCreateModal() {
  editingPostId.value = null
  postForm.value = { title: '', place: '', category: '여행 후기', content: '', password: '', contentid: '' }
  isWritingPost.value = true
}

async function openEditModal() {
  editingPostId.value = selectedPost.value.id
  postForm.value = {
    title: selectedPost.value.title,
    place: selectedPost.value.place || '',
    category: selectedPost.value.category,
    content: selectedPost.value.content,
    password: '',
    contentid: selectedPost.value.contentid || ''
  }
  isWritingPost.value = true
}

async function savePost() {
  try {
    if (editingPostId.value) {
      await api.updatePost(editingPostId.value, postForm.value)
      isWritingPost.value = false
      await loadPosts()
      selectedPost.value = await api.getPost(editingPostId.value)
      alert('게시글이 수정되었습니다.')
    } else {
      const created = await api.createPost(postForm.value)
      isWritingPost.value = false
      await loadPosts()
      if (created?.id) selectedPost.value = await api.getPost(created.id)
    }
  } catch (err) {
    alert(err.message)
  }
}

async function openPost(post) {
  selectedPost.value = await api.getPost(post.id)
}

async function likePost() {
  await api.likePost(selectedPost.value.id)
  selectedPost.value = await api.getPost(selectedPost.value.id)
  await loadPosts()
}

async function deletePost() {
  if (!deletePassword.value) return
  await api.deletePost(selectedPost.value.id, deletePassword.value)
  selectedPost.value = null
  deletePassword.value = ''
  await loadPosts()
}

async function sendChat() {
  const message = chatInput.value.trim()
  if (!message || loading.value) return
  chatMessages.value.push({ role: 'user', content: message })
  chatInput.value = ''
  loading.value = true
  
  const tempMessage = {
    role: 'assistant',
    content: '',
    locations: [],
    sources: []
  }
  chatMessages.value.push(tempMessage)
  const proxyMessage = chatMessages.value[chatMessages.value.length - 1]

  try {
    await api.chat(
      { message, history: chatMessages.value.slice(0, -2) },
      (chunkText) => {
        proxyMessage.content += chunkText
        scrollToBottom()
      },
      (metadata) => {
        proxyMessage.locations = metadata.referenced_items || []
        proxyMessage.sources = metadata.sources || []
        scrollToBottom()
      }
    )
  } catch (err) {
    proxyMessage.content += `\n\n**오류 발생:** ${err.message}`
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = document.querySelector('.chat-stream')
    if (el) el.scrollTop = el.scrollHeight
  })
}

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(text))
}

function toggleChat() {
  isChatOpen.value = !isChatOpen.value
  if (isChatOpen.value) {
    nextTick(() => document.querySelector('.chat-input input')?.focus())
  }
}
</script>

<template>
  <main class="app">
    <aside class="sidebar">
      <div class="brand">
        <div class="logo-box">LH</div>
        <div>
          <h1>LocalHub</h1>
          <p>프리미엄 지역 정보 플랫폼</p>
        </div>
      </div>
      <nav>
        <button :class="{ active: activeTab === 'places' }" @click="activeTab = 'places'">
          <MapPin :size="20" /> <span>장소 탐색</span>
        </button>
        <button :class="{ active: activeTab === 'posts' }" @click="activeTab = 'posts'">
          <MessageSquareText :size="20" /> <span>커뮤니티</span>
        </button>
      </nav>
    </aside>

    <transition name="fade" mode="out-in">
      <section v-if="activeTab === 'places'" class="workspace places" key="places">
        <section class="map-card glass-panel">
          <div class="toolbar">
            <label class="search">
              <Search :size="18" />
              <input v-model="searchText" placeholder="장소명, 주소를 검색해보세요" @keyup.enter="loadLocations" />
            </label>
            <div class="filters">
              <select v-model="typeId" @change="loadLocations">
                <option v-for="category in categories" :key="category.id" :value="category.id">
                  {{ category.label }}
                </option>
              </select>
              <button class="primary" @click="loadLocations">검색</button>
            </div>
          </div>
          <div id="map"></div>
        </section>

        <section class="list-card glass-panel">
          <header class="list-header">
            <h2>탐색 결과 <span class="badge">{{ locations.length }}</span></h2>
          </header>
          <div class="list-scroll">
            <transition-group name="list">
              <button
                v-for="location in shownLocations"
                :key="location.contentid"
                class="row-item"
                :class="{ selected: selectedLocation?.contentid === location.contentid }"
                @click="openLocation(location)"
              >
                <div class="thumb-wrapper">
                  <img v-if="location.firstimage" :src="location.firstimage" alt="" />
                  <span v-else class="thumb-placeholder">{{ location.contenttypename[0] }}</span>
                </div>
                <div class="row-content">
                  <strong>{{ location.title }}</strong>
                  <small>{{ location.addr1 || location.contenttypename }}</small>
                </div>
                <ChevronRight class="row-icon" :size="16" />
              </button>
            </transition-group>
          </div>
        </section>

        <transition name="slide-up">
          <section v-if="selectedLocation" class="detail-card glass-panel">
            <div class="detail-hero">
              <img v-if="selectedLocation.firstimage" :src="selectedLocation.firstimage" alt="" />
              <div v-else class="hero-placeholder"></div>
              <div class="hero-overlay">
                <span class="eyebrow badge">{{ selectedLocation.contenttypename }}</span>
                <h2>{{ selectedLocation.title }}</h2>
                <p><MapPin :size="14" style="display:inline;vertical-align:middle;margin-right:4px"/>{{ selectedLocation.addr1 }} {{ selectedLocation.addr2 }}</p>
              </div>
            </div>
            
            <div class="detail-body">
              <div v-if="Object.keys(selectedLocation.type_fields || {}).length" class="fields-grid">
                <div v-for="(val, key) in selectedLocation.type_fields" :key="key" class="field-item">
                  <span class="field-key">{{ key }}</span>
                  <span class="field-val">{{ val }}</span>
                </div>
              </div>
              <p v-else class="empty-state">추가 상세 정보가 없습니다.</p>

              <div class="nearby-foods mt-6" v-if="selectedLocation.nearby_restaurants && selectedLocation.nearby_restaurants.length">
                <h3 class="text-lg font-bold text-gray-800 mb-3">🍽 주변 추천 식당</h3>
                <div class="grid grid-cols-2 gap-3">
                  <button v-for="place in selectedLocation.nearby_restaurants" :key="place.contentid" class="nearby-card" @click="openLocation(place)">
                    <img v-if="place.firstimage" :src="place.firstimage" alt="" />
                    <div v-else class="nearby-placeholder"></div>
                    <div class="nearby-content">
                      <h4 :title="place.title">{{ place.title }}</h4>
                      <p>{{ place.distance_km }}km</p>
                    </div>
                  </button>
                </div>
              </div>

              <div class="nearby-foods mt-6" v-if="selectedLocation.nearby_accommodations && selectedLocation.nearby_accommodations.length">
                <h3 class="text-lg font-bold text-gray-800 mb-3">🏨 주변 추천 숙소</h3>
                <div class="grid grid-cols-2 gap-3">
                  <button v-for="place in selectedLocation.nearby_accommodations" :key="place.contentid" class="nearby-card" @click="openLocation(place)">
                    <img v-if="place.firstimage" :src="place.firstimage" alt="" />
                    <div v-else class="nearby-placeholder"></div>
                    <div class="nearby-content">
                      <h4 :title="place.title">{{ place.title }}</h4>
                      <p>{{ place.distance_km }}km</p>
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </section>
        </transition>
      </section>

      <section v-else-if="activeTab === 'posts'" class="workspace posts" key="posts">
        <section class="list-card glass-panel">
          <header class="list-header" style="flex-direction: column; align-items: stretch; gap: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <h2>커뮤니티 글 목록</h2>
              <button class="primary" style="height: 32px; padding: 0 16px; font-size: 0.85rem;" @click="openCreateModal">새 글 작성</button>
            </div>
            <div class="search" style="height: 40px;">
              <Search :size="16" />
              <input v-model="postSearchText" placeholder="검색어 입력" @keyup.enter="loadPosts" />
            </div>
            <div class="filters">
              <select v-model="postSearchType" style="height: 36px; padding: 0 10px; font-size: 0.85rem;" @change="loadPosts">
                <option value="both">제목+내용</option>
                <option value="title">제목</option>
                <option value="content">내용</option>
              </select>
              <select v-model="postSortBy" style="height: 36px; padding: 0 10px; font-size: 0.85rem;" @change="loadPosts">
                <option value="latest">최신순</option>
                <option value="likes">추천순</option>
              </select>
              <button class="primary" style="height: 36px; padding: 0 16px; font-size: 0.85rem;" @click="loadPosts">검색</button>
            </div>
          </header>
          <div class="list-scroll">
            <transition-group name="list">
              <button v-for="post in posts" :key="post.id" class="post-row" :class="{ selected: selectedPost?.id === post.id }" @click="openPost(post)">
                <div class="post-row-content">
                  <strong>{{ post.title }}</strong>
                  <small>{{ post.category }} · {{ post.place_name || '장소 없음' }}</small>
                </div>
                <div class="post-meta">
                  <span><Heart :size="12" /> {{ post.like_count }}</span>
                </div>
              </button>
            </transition-group>
          </div>
        </section>

        <transition name="fade" mode="out-in">
          <section v-if="selectedPost" class="post-detail glass-panel" :key="selectedPost.id">
            <header class="post-header">
              <div class="post-tags">
                <span class="badge category">{{ selectedPost.category }}</span>
                <span v-if="selectedPost.place" class="badge place"><MapPin :size="12" style="margin-right:4px"/>{{ selectedPost.place }}</span>
              </div>
              <h2>{{ selectedPost.title }}</h2>
              <small class="post-date">{{ new Date(selectedPost.created_at).toLocaleString() }} · 조회 {{ selectedPost.view_count }}</small>
            </header>
            <div class="post-body">
              <p>{{ selectedPost.content }}</p>
            </div>
            <footer class="post-actions">
              <button class="action-btn like-btn" @click="likePost"><Heart :size="18" /> 좋아요 {{ selectedPost.like_count }}</button>
              <div class="delete-group">
                <input v-model="deletePassword" class="glass-input" type="password" placeholder="비밀번호" />
                <button class="action-btn edit-btn" style="background: white; border: 1px solid var(--border); margin-right: 4px;" @click="openEditModal">수정</button>
                <button class="action-btn danger-btn" @click="deletePost"><Trash2 :size="18" /> 삭제</button>
              </div>
            </footer>
          </section>
          <section v-else class="post-detail glass-panel empty-selection">
            <MessageSquareText :size="48" opacity="0.2" />
            <p>게시글을 선택하거나 새 글을 작성해보세요.</p>
          </section>
        </transition>
      </section>
    </transition>

    <!-- Write Post Modal -->
    <transition name="scale-up">
      <div v-if="isWritingPost" class="chatbot-overlay" @click.self="isWritingPost = false">
        <form class="form-card glass-panel" style="width: 500px; margin: auto; padding: 32px; position: relative;" @submit.prevent="savePost">
          <header class="chat-header" style="margin-bottom: 16px; border-bottom: none; padding: 0;">
            <h2 style="font-size: 1.4rem; font-weight: 800;">{{ editingPostId ? '게시글 수정' : '새 글 작성' }}</h2>
            <button type="button" class="close-btn" @click="isWritingPost = false"><X :size="24" /></button>
          </header>
          <div class="form-group">
            <input v-model="postForm.title" required placeholder="제목을 입력하세요" class="glass-input" />
          </div>
          <div class="form-row">
            <select v-model="postForm.category" class="glass-input" style="flex: 1;">
              <option>여행 후기</option>
              <option>맛집 추천</option>
              <option>축제 정보</option>
              <option>자유</option>
            </select>
            <div style="flex: 2; position: relative;">
              <input v-model="postForm.place" placeholder="관련 장소명 검색 (선택)" class="glass-input" @focus="showPlaceSuggestions = true" @blur="hidePlaceSuggestions" />
              <div v-if="showPlaceSuggestions && placeSuggestions.length > 0" class="suggestions-dropdown">
                <button type="button" v-for="sugg in placeSuggestions" :key="sugg.contentid" class="suggestion-item" @mousedown.prevent="selectPlaceSuggestion(sugg)">
                  <MapPin :size="14" style="margin-right: 6px; color: var(--primary); flex-shrink: 0;" />
                  <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ sugg.title }}</span>
                </button>
              </div>
            </div>
          </div>
          <div class="form-group">
            <textarea v-model="postForm.content" required placeholder="내용을 자유롭게 작성해주세요..." class="glass-input"></textarea>
          </div>
          <div class="form-group">
            <input v-model="postForm.password" required type="password" placeholder="수정/삭제용 비밀번호 (필수)" class="glass-input" />
          </div>
          <button class="primary submit-btn" type="submit">{{ editingPostId ? '수정하기' : '게시물 등록하기' }}</button>
        </form>
      </div>
    </transition>

    <!-- Floating Chatbot Button -->
    <button class="chatbot-fab" @click="toggleChat" :class="{ pulse: !isChatOpen && chatMessages.length === 1 }">
      <Bot :size="28" />
    </button>

    <!-- Chatbot Fullscreen Modal -->
    <transition name="scale-up">
      <div v-if="isChatOpen" class="chatbot-overlay" @click.self="toggleChat">
        <section class="chat-modal glass-panel">
          <header class="chat-header">
            <div class="chat-title">
              <div class="bot-icon-wrapper"><Bot :size="24" /></div>
              <div>
                <h2>AI 여행 가이드</h2>
                <p>무엇이든 물어보세요! FAISS 기반 문서 탐색</p>
              </div>
            </div>
            <button class="close-btn" @click="toggleChat"><X :size="24" /></button>
          </header>

          <div class="chat-stream">
            <transition-group name="list">
              <article v-for="(message, index) in chatMessages" :key="index" class="bubble" :class="message.role">
                <div class="bubble-content">
                  <div v-if="message.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(message.content)"></div>
                  <p v-else>{{ message.content }}</p>
                  
                  <div v-if="message.locations?.length" class="chips">
                    <button
                      v-for="location in message.locations"
                      :key="location.contentid"
                      @click="toggleChat(); activeTab = 'places'; openLocation(location)"
                      class="chip-btn"
                    >
                      <MapPin :size="14" /> {{ location.title }}
                    </button>
                  </div>
                  
                  <div v-if="message.sources?.length" class="sources">
                    <span v-for="source in message.sources" :key="source.chunk_id" class="source-tag">
                      출처: {{ source.source }}
                    </span>
                  </div>
                </div>
              </article>
            </transition-group>
            
            <article v-if="loading" class="bubble assistant loading">
              <div class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </article>
          </div>

          <form class="chat-input-area" @submit.prevent="sendChat">
            <div class="input-wrapper">
              <input v-model="chatInput" placeholder="대전 여행 코스 추천해줘..." class="glass-input" :disabled="loading" />
              <button type="submit" class="send-btn" :disabled="!chatInput.trim() || loading">
                <Send :size="20" />
              </button>
            </div>
          </form>
        </section>
      </div>
    </transition>

    <transition name="slide-up">
      <div v-if="error" class="toast-error">
        {{ error }}
        <button @click="error = ''"><X :size="16" /></button>
      </div>
    </transition>
  </main>
</template>
