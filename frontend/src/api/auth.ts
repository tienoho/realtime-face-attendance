import api from './axios'
import { ApiEnvelope, unwrapEnvelope } from './dto'

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  token: string
  user_id: number
  username: string
}

export const authApi = {
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const response = await api.post<ApiEnvelope<LoginResponse>>('/login', data)
    return unwrapEnvelope(response.data)
  },

  logout: () => {
    localStorage.removeItem('fa_token')
  },
}
