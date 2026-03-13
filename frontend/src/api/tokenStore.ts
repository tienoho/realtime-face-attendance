/**
 * Token Store - Centralized token management for the frontend
 * 
 * C-AUTH-001 FIX: Provides single source of truth for authentication token
 * - AuthContext stores token in memory AND notifies this store
 * - Axios interceptor reads from this store
 * - SocketContext reads from this store
 * 
 * SESSION-PERSISTENCE FIX: Added localStorage support for "Remember Me" feature
 * - If user checks "Remember Me", token is saved to localStorage
 * - On page load, token is restored from localStorage
 * - Security is maintained by:
 *   1. Using short-lived access tokens (1 hour)
 *   2. Implementing token refresh mechanism
 *   3. Clearing token on 401 responses
 * 
 * REFRESH-TOKEN FIX: Now stores both access token and refresh token
 * - Refresh token allows getting new access tokens without re-login
 * - Both tokens are persisted together when "Remember Me" is checked
 */

// Event listener type
type TokenChangeListener = (token: string | null) => void

// LocalStorage keys
const TOKEN_STORAGE_KEY = 'face_attendance_token'
const REFRESH_TOKEN_KEY = 'face_attendance_refresh_token'

interface TokenPair {
  accessToken: string | null
  refreshToken: string | null
}

class TokenStore {
  private tokens: TokenPair = { accessToken: null, refreshToken: null }
  private listeners: TokenChangeListener[] = []
  private initialized = false
  
  constructor() {
    // SESSION-PERSISTENCE FIX: Initialize from localStorage if available
    this._initializeFromStorage()
  }
  
  private _initializeFromStorage(): void {
    if (this.initialized) return
    this.initialized = true
    
    try {
      const storedAccess = localStorage.getItem(TOKEN_STORAGE_KEY)
      const storedRefresh = localStorage.getItem(REFRESH_TOKEN_KEY)
      if (storedAccess) {
        this.tokens.accessToken = storedAccess
        this.tokens.refreshToken = storedRefresh
        console.log('Tokens restored from localStorage')
      }
    } catch (e) {
      console.error('Failed to load tokens from localStorage:', e)
    }
  }
  
  /**
   * Set both access token and refresh token
   * @param accessToken The access token
   * @param refreshToken The refresh token
   * @param persist If true, also save to localStorage
   */
  setTokens(accessToken: string | null, refreshToken: string | null, persist = false): void {
    this.tokens.accessToken = accessToken
    this.tokens.refreshToken = refreshToken
    
    // SESSION-PERSISTENCE FIX: Save to localStorage if requested
    if (persist && accessToken && refreshToken) {
      try {
        localStorage.setItem(TOKEN_STORAGE_KEY, accessToken)
        localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
        console.log('Tokens saved to localStorage')
      } catch (e) {
        console.error('Failed to save tokens to localStorage:', e)
      }
    } else if (!accessToken) {
      // Clear from localStorage when logging out
      try {
        localStorage.removeItem(TOKEN_STORAGE_KEY)
        localStorage.removeItem(REFRESH_TOKEN_KEY)
      } catch (e) {
        console.error('Failed to clear tokens from localStorage:', e)
      }
    }
    
    this.notifyListeners()
  }
  
  /**
   * Set only the access token (for backward compatibility)
   * @param token The access token
   * @param persist If true, also save to localStorage
   */
  setToken(token: string | null, persist = false): void {
    this.setTokens(token, this.tokens.refreshToken, persist)
  }
  
  /**
   * Get the current access token (for axios, socket, etc.)
   */
  getToken(): string | null {
    return this.tokens.accessToken
  }
  
  /**
   * Get the refresh token
   */
  getRefreshToken(): string | null {
    return this.tokens.refreshToken
  }
  
  /**
   * Clear both tokens (for logout)
   */
  clearToken(): void {
    this.tokens.accessToken = null
    this.tokens.refreshToken = null
    try {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
    } catch (e) {
      console.error('Failed to clear tokens from localStorage:', e)
    }
    this.notifyListeners()
  }
  
  /**
   * Check if token exists in storage
   */
  hasStoredToken(): boolean {
    return this.tokens.accessToken !== null
  }
  
  /**
   * Check if refresh token exists
   */
  hasRefreshToken(): boolean {
    return this.tokens.refreshToken !== null
  }
  
  /**
   * Register a listener for token changes
   */
  addListener(listener: TokenChangeListener): () => void {
    this.listeners.push(listener)
    // Return unsubscribe function
    return () => {
      const index = this.listeners.indexOf(listener)
      if (index > -1) {
        this.listeners.splice(index, 1)
      }
    }
  }
  
  private notifyListeners(): void {
    this.listeners.forEach(listener => {
      try {
        listener(this.tokens.accessToken)
      } catch (e) {
        console.error('Token listener error:', e)
      }
    })
  }
}

// Singleton instance
export const tokenStore = new TokenStore()
