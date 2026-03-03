import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { authApi, LoginRequest } from '../api/auth'

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
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

// C-SEC-004 FIX: Use memory-only storage instead of localStorage to prevent XSS
// Token is stored in memory only, not persisted to disk
const TOKEN_STORAGE_KEY = 'fa_token'

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
  const [isLoading, setIsLoading] = useState(true)

  // C-SEC-004 FIX: No localStorage usage - token is memory-only
  // User must re-login after page refresh (security trade-off)
  useEffect(() => {
    // Token not persisted - user must login again after refresh
    // This prevents XSS from stealing tokens via localStorage
    setIsLoading(false)
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const response = await authApi.login({ username, password } as LoginRequest)
    
    // Verify token expiration before saving
    const payload = decodeJWT(response.token)
    if (!payload || isTokenExpired(payload)) {
      throw new Error('Invalid token received from server')
    }
    
    // C-SEC-004 FIX: Store token in memory only, not localStorage
    setToken(response.token)
    setUser({
      user_id: response.user_id,
      username: response.username,
    })
  }, [])

  const logout = useCallback(() => {
    // C-SEC-004 FIX: Clear memory-only state
    setToken(null)
    setUser(null)
  }, [])

  const value = {
    user,
    token,
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
