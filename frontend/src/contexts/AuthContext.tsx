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

  useEffect(() => {
    const storedToken = localStorage.getItem('fa_token')
    if (storedToken) {
      try {
        // Decode and verify expiration
        const payload = decodeJWT(storedToken)
        
        if (!payload) {
          // Invalid token format, remove it
          localStorage.removeItem('fa_token')
        } else if (isTokenExpired(payload)) {
          // Token expired, remove it
          console.warn('Token expired, please login again')
          localStorage.removeItem('fa_token')
        } else {
          // Token valid, set user
          setUser({
            user_id: payload.user_id,
            username: payload.username,
          })
          setToken(storedToken)
        }
      } catch {
        localStorage.removeItem('fa_token')
      }
    }
    setIsLoading(false)
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const response = await authApi.login({ username, password } as LoginRequest)
    
    // Verify token expiration before saving
    const payload = decodeJWT(response.token)
    if (!payload || isTokenExpired(payload)) {
      throw new Error('Invalid token received from server')
    }
    
    localStorage.setItem('fa_token', response.token)
    setToken(response.token)
    setUser({
      user_id: response.user_id,
      username: response.username,
    })
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('fa_token')
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
