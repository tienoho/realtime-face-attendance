import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Box,
  Button,
  Typography,
  IconButton,
  Card,
  CardMedia,
  Grid,
  Alert,
  LinearProgress,
} from '@mui/material'
import {
  CameraAlt,
  FlipCameraAndroid,
  Close,
  Check,
  Refresh,
} from '@mui/icons-material'

interface FaceCaptureProps {
  onCapture: (images: string[]) => void
  onClose: () => void
  targetCount?: number
}

export default function FaceCapture({
  onCapture,
  onClose,
  targetCount = 10,
}: FaceCaptureProps) {
  // Validate and normalize targetCount (min: 1, max: 50)
  const validatedTargetCount = Math.max(1, Math.min(targetCount, 50))

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [capturedImages, setCapturedImages] = useState<string[]>([])
  const [isCapturing, setIsCapturing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('user')
  const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Initialize camera
  useEffect(() => {
    initCamera()
    return () => {
      // Properly cleanup stream on unmount
      if (stream) {
        stream.getTracks().forEach((track) => track.stop())
      }
      if (captureIntervalRef.current) {
        clearInterval(captureIntervalRef.current)
      }
    }
  }, [facingMode])

  const initCamera = async () => {
    try {
      setError(null)
      stopCamera()

      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode,
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      })

      setStream(mediaStream)
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
      }
    } catch (err) {
      console.error('Camera error:', err)
      setError('Không thể truy cập camera. Vui lòng cấp quyền camera.')
    }
  }

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop())
      setStream(null)
    }
    if (captureIntervalRef.current) {
      clearInterval(captureIntervalRef.current)
      captureIntervalRef.current = null
    }
  }

  const captureFrame = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return null

    const video = videoRef.current
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')

    if (!ctx) return null

    // Set canvas size to match video
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight

    // Draw video frame to canvas
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

    // Get base64 data
    return canvas.toDataURL('image/jpeg', 0.8)
  }, [])

  const startAutoCapture = async () => {
    if (capturedImages.length >= validatedTargetCount) return

    setIsCapturing(true)

    // Capture frames at intervals
    captureIntervalRef.current = setInterval(() => {
      const imageData = captureFrame()
      if (imageData) {
        setCapturedImages((prev) => {
          if (prev.length >= validatedTargetCount) {
            // Stop capturing when target reached
            if (captureIntervalRef.current) {
              clearInterval(captureIntervalRef.current)
              captureIntervalRef.current = null
            }
            setIsCapturing(false)
            return prev
          }
          return [...prev, imageData]
        })
      }
    }, 500) // Capture every 500ms
  }

  const stopAutoCapture = () => {
    if (captureIntervalRef.current) {
      clearInterval(captureIntervalRef.current)
      captureIntervalRef.current = null
    }
    setIsCapturing(false)
  }

  const captureSingle = () => {
    const imageData = captureFrame()
    if (imageData) {
      setCapturedImages((prev) => {
        if (prev.length >= validatedTargetCount) {
          return prev
        }
        return [...prev, imageData]
      })
    }
  }

  const removeImage = (index: number) => {
    setCapturedImages((prev) => prev.filter((_, i) => i !== index))
  }

  const clearAll = () => {
    setCapturedImages([])
  }

  const toggleCamera = () => {
    setFacingMode((prev) => (prev === 'user' ? 'environment' : 'user'))
  }

  const handleDone = () => {
    if (capturedImages.length > 0) {
      onCapture(capturedImages)
    }
  }

  const progress = (capturedImages.length / validatedTargetCount) * 100

  return (
    <Box
      sx={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        bgcolor: 'rgba(0,0,0,0.9)',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        p: 2,
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 2,
        }}
      >
        <Typography variant="h6" color="white">
          Chụp ảnh khuôn mặt ({capturedImages.length}/{validatedTargetCount})
        </Typography>
        <IconButton onClick={onClose} sx={{ color: 'white' }}>
          <Close />
        </IconButton>
      </Box>

      {/* Error */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Main content */}
      <Box
        sx={{
          display: 'flex',
          flex: 1,
          gap: 2,
          overflow: 'hidden',
        }}
      >
        {/* Camera preview */}
        <Box
          sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
          }}
        >
          <Box
            sx={{
              position: 'relative',
              width: '100%',
              maxWidth: 640,
              aspectRatio: '4/3',
              bgcolor: 'black',
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                transform: facingMode === 'user' ? 'scaleX(-1)' : 'none',
              }}
            />
            <canvas ref={canvasRef} style={{ display: 'none' }} />

            {/* Capture overlay */}
            {isCapturing && (
              <Box
                sx={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  border: '4px solid #4caf50',
                  borderRadius: 2,
                  animation: 'pulse 0.5s infinite',
                  '@keyframes pulse': {
                    '0%': { opacity: 1 },
                    '50%': { opacity: 0.5 },
                    '100%': { opacity: 1 },
                  },
                }}
              />
            )}
          </Box>

          {/* Controls */}
          <Box
            sx={{
              display: 'flex',
              gap: 2,
              mt: 2,
              justifyContent: 'center',
            }}
          >
            <IconButton
              onClick={toggleCamera}
              sx={{
                bgcolor: 'rgba(255,255,255,0.1)',
                color: 'white',
                '&:hover': { bgcolor: 'rgba(255,255,255,0.2)' },
              }}
            >
              <FlipCameraAndroid />
            </IconButton>

            {isCapturing ? (
              <Button
                variant="contained"
                color="error"
                onClick={stopAutoCapture}
                startIcon={<Close />}
              >
                Dừng
              </Button>
            ) : (
              <Button
                variant="contained"
                color="primary"
                onClick={startAutoCapture}
                disabled={capturedImages.length >= validatedTargetCount}
                startIcon={<CameraAlt />}
              >
                Chụp tự động
              </Button>
            )}

            <Button
              variant="outlined"
              onClick={captureSingle}
              disabled={capturedImages.length >= validatedTargetCount || isCapturing}
              sx={{ color: 'white', borderColor: 'white' }}
            >
              Chụp 1 ảnh
            </Button>
          </Box>

          {/* Progress */}
          <Box sx={{ width: '100%', maxWidth: 640, mt: 2 }}>
            <LinearProgress
              variant="determinate"
              value={progress}
              sx={{
                height: 8,
                borderRadius: 4,
                bgcolor: 'rgba(255,255,255,0.2)',
                '& .MuiLinearProgress-bar': {
                  bgcolor: progress >= 100 ? '#4caf50' : '#2196f3',
                },
              }}
            />
            <Typography variant="body2" color="white" sx={{ mt: 1, textAlign: 'center' }}>
              {capturedImages.length}/{validatedTargetCount} ảnh
              {progress >= 100 && ' - Hoàn thành!'}
            </Typography>
          </Box>
        </Box>

        {/* Captured images */}
        <Box
          sx={{
            width: 300,
            bgcolor: 'rgba(255,255,255,0.05)',
            borderRadius: 2,
            p: 2,
            overflowY: 'auto',
          }}
        >
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              mb: 2,
            }}
          >
            <Typography variant="subtitle1" color="white">
              Ảnh đã chụp
            </Typography>
            <Button
              size="small"
              onClick={clearAll}
              startIcon={<Refresh />}
              sx={{ color: 'white' }}
            >
              Xóa all
            </Button>
          </Box>

          <Grid container spacing={1}>
            {capturedImages.map((img, index) => (
              <Grid item xs={6} key={index}>
                <Card sx={{ position: 'relative' }}>
                  <CardMedia
                    component="img"
                    height="80"
                    image={img}
                    sx={{
                      transform: facingMode === 'user' ? 'scaleX(-1)' : 'none',
                    }}
                  />
                  <IconButton
                    size="small"
                    onClick={() => removeImage(index)}
                    sx={{
                      position: 'absolute',
                      top: 2,
                      right: 2,
                      bgcolor: 'rgba(0,0,0,0.5)',
                      color: 'white',
                      '&:hover': { bgcolor: 'red' },
                      width: 24,
                      height: 24,
                    }}
                  >
                    <Close sx={{ fontSize: 16 }} />
                  </IconButton>
                </Card>
              </Grid>
            ))}
          </Grid>

          {capturedImages.length === 0 && (
            <Typography color="rgba(255,255,255,0.5)" textAlign="center" py={4}>
              Chưa có ảnh nào
            </Typography>
          )}
        </Box>
      </Box>

      {/* Footer */}
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 2,
          mt: 2,
        }}
      >
        <Button variant="outlined" onClick={onClose} sx={{ color: 'white', borderColor: 'white' }}>
          Hủy
        </Button>
        <Button
          variant="contained"
          onClick={handleDone}
          disabled={capturedImages.length === 0}
          startIcon={<Check />}
        >
          Hoàn thành ({capturedImages.length})
        </Button>
      </Box>
    </Box>
  )
}
