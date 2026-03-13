import api from './axios'
import { tokenStore } from './tokenStore'
import { ApiEnvelope, unwrapEnvelope } from './dto'

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user_id: number
  username: string
}

export const authApi = {
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const response = await api.post<ApiEnvelope<LoginResponse>>('/login', data)
    return unwrapEnvelope(response.data)
  },

  // Refresh access token using refresh token
  refreshToken: async (refreshToken: string): Promise<LoginResponse> => {
    const response = await api.post<ApiEnvelope<LoginResponse>>('/refresh', {
      refresh_token: refreshToken,
    })
    return unwrapEnvelope(response.data)
  },

  logout: (refreshToken?: string) => {
    // Use tokenStore to clear token consistently
    tokenStore.clearToken()
    
    // Optionally notify server to invalidate refresh token
    if (refreshToken) {
      api.post('/logout', { refresh_token: refreshToken }).catch(() => {
        // Ignore logout errors
      })
    }
  },
}
