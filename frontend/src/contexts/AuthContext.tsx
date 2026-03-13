import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { authApi, LoginRequest } from '../api/auth'
import { tokenStore } from '../api/tokenStore'

interface User {
  user_id: number
  username: string
}

interface JWTPayload {
  user_id: number
  username: string
  exp: number
  iat: number
}

interface AuthContextType {
  user: User | null
  token: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

// Helper to safely decode JWT without verification (just for reading claims)
function decodeJWT(token: string): JWTPayload | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = JSON.parse(atob(parts[1]))
    return payload as JWTPayload
  } catch {
    return null
  }
}

// Check if token is expired
function isTokenExpired(payload: JWTPayload): boolean {
  if (!payload.exp) return true
  return Date.now() >= payload.exp * 1000
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [refreshToken, setRefreshToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // SESSION-PERSISTENCE FIX: Load token from tokenStore (which may have restored from localStorage)
  useEffect(() => {
    // Check if tokenStore has a stored token (from localStorage)
    const storedToken = tokenStore.getToken()
    const storedRefreshToken = tokenStore.getRefreshToken()
    
    if (storedToken) {
      // Verify token is not expired
      const payload = decodeJWT(storedToken)
      if (payload && !isTokenExpired(payload)) {
        // Token is valid - restore session
        setToken(storedToken)
        setRefreshToken(storedRefreshToken)
        setUser({
          user_id: payload.user_id,
          username: payload.username,
        })
        console.log('Session restored from stored token')
      } else if (storedRefreshToken && payload) {
        // Access token expired but we have refresh token - try to refresh
        console.log('Access token expired, will try to refresh...')
        setRefreshToken(storedRefreshToken)
        setIsRefreshing(true)
      } else {
        // Token expired - clear it
        tokenStore.clearToken()
        console.log('Stored token expired, cleared')
      }
    }
    setIsLoading(false)
  }, [])

  // Auto-refresh token when it's about to expire (within 5 minutes)
  useEffect(() => {
    if (!refreshToken || isRefreshing) return

    const checkAndRefreshToken = async () => {
      const currentToken = tokenStore.getToken()
      if (!currentToken) return

      const payload = decodeJWT(currentToken)
      if (!payload) return

      // Check if token expires within 5 minutes
      const expiresIn = payload.exp * 1000 - Date.now()
      if (expiresIn < 5 * 60 * 1000 && expiresIn > 0) {
        // Token about to expire, refresh it
        try {
          setIsRefreshing(true)
          const newTokens = await authApi.refreshToken(refreshToken)
          
          // Update tokens
          const newPayload = decodeJWT(newTokens.token)
          if (newPayload && !isTokenExpired(newPayload)) {
            const shouldPersist = tokenStore.getRefreshToken() !== null
            tokenStore.setTokens(newTokens.token, newTokens.refresh_token, shouldPersist)
            setToken(newTokens.token)
            setRefreshToken(newTokens.refresh_token)
            console.log('Token auto-refreshed')
          }
        } catch (error) {
          console.error('Failed to refresh token:', error)
          // If refresh fails, logout user
          logout()
        } finally {
          setIsRefreshing(false)
        }
      }
    }

    // Check immediately and then every minute
    checkAndRefreshToken()
    const interval = setInterval(checkAndRefreshToken, 60 * 1000)

    return () => clearInterval(interval)
  }, [refreshToken, isRefreshing])

  // SESSION-PERSISTENCE FIX: Add rememberMe parameter
  const login = useCallback(async (username: string, password: string, rememberMe = false) => {
    const response = await authApi.login({ username, password } as LoginRequest)
    
    // Verify token expiration before saving
    const payload = decodeJWT(response.token)
    if (!payload || isTokenExpired(payload)) {
      throw new Error('Invalid token received from server')
    }
    
    // Store tokens with optional persistence
    tokenStore.setTokens(response.token, response.refresh_token, rememberMe)
    setToken(response.token)
    setRefreshToken(response.refresh_token)
    setUser({
      user_id: response.user_id,
      username: response.username,
    })
  }, [])

  const logout = useCallback(() => {
    // Get refresh token to notify server
    const rt = tokenStore.getRefreshToken()
    
    // Clear memory and localStorage state
    setToken(null)
    setRefreshToken(null)
    tokenStore.clearToken()
    setUser(null)
    
    // Notify server to invalidate refresh token
    if (rt) {
      authApi.logout(rt)
    }
  }, [])

  const value = {
    user,
    token,
    refreshToken,
    isAuthenticated: !!token,
    isLoading,
    login,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
