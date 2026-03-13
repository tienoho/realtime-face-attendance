import axios from 'axios'
import { tokenStore } from './tokenStore'
import { authApi } from './auth'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Track if we're currently refreshing to prevent multiple refresh calls
let isRefreshing = false
let failedQueue: Array<{
  resolve: (value?: any) => void
  reject: (reason?: any) => void
}> = []

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error)
    } else {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    // C-AUTH-001 FIX: Use tokenStore instead of localStorage
    // This ensures we get the token from AuthContext's memory store
    const token = tokenStore.getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle errors and auto-refresh token
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // If 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // Already refreshing, add to queue
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then(token => {
            originalRequest.headers.Authorization = `Bearer ${token}`
            return api(originalRequest)
          })
          .catch(err => {
            return Promise.reject(err)
          })
      }

      originalRequest._retry = true
      isRefreshing = true

      const refreshToken = tokenStore.getRefreshToken()
      
      if (refreshToken) {
        try {
          // Try to refresh the token
          const newTokens = await authApi.refreshToken(refreshToken)
          
          // Update stored tokens (persist if there was a refresh token)
          tokenStore.setTokens(newTokens.token, newTokens.refresh_token, !!refreshToken)
          
          // Process queued requests
          processQueue(null, newTokens.token)
          
          // Retry the original request
          originalRequest.headers.Authorization = `Bearer ${newTokens.token}`
          return api(originalRequest)
        } catch (refreshError) {
          // Refresh failed, clear tokens and redirect to login
          processQueue(refreshError as Error, null)
          tokenStore.clearToken()
          window.location.href = '/login'
          return Promise.reject(refreshError)
        } finally {
          isRefreshing = false
        }
      }

      // No refresh token available, redirect to login
      tokenStore.clearToken()
      window.location.href = '/login'
    }

    const apiMessage =
      error?.response?.data?.error?.message ||
      error?.response?.data?.message

    if (apiMessage) {
      error.message = apiMessage
    }

    return Promise.reject(error)
  }
)

export default api
