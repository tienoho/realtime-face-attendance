export interface ApiErrorPayload {
  code: string
  message: string
  details?: unknown
}

export interface ApiSuccessEnvelope<T> {
  success: true
  message: string
  data: T
  meta?: Record<string, unknown>
}

export interface ApiErrorEnvelope {
  success: false
  message: string
  error: ApiErrorPayload
}

export type ApiEnvelope<T> = ApiSuccessEnvelope<T> | ApiErrorEnvelope

export function unwrapEnvelope<T>(payload: ApiEnvelope<T>): T {
  if (!payload.success) {
    throw new Error(payload.error?.message || payload.message || 'Request failed')
  }
  return payload.data
}

export function unwrapEnvelopeWithMessage<T extends Record<string, unknown>>(
  payload: ApiEnvelope<T>
): T & { message: string } {
  if (!payload.success) {
    throw new Error(payload.error?.message || payload.message || 'Request failed')
  }
  return {
    ...payload.data,
    message: payload.message,
  } as T & { message: string }
}
