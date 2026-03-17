import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  CircularProgress,
  FormControlLabel,
  Checkbox,
  InputAdornment,
  IconButton,
  useTheme,
  alpha,
} from '@mui/material'
import {
  Visibility,
  VisibilityOff,
  Videocam as VideocamIcon,
} from '@mui/icons-material'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()
  const theme = useTheme()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    
    // Input validation
    if (!username.trim() || !password.trim()) {
      setError('Username and password are required')
      return
    }
    
    if (username.length < 3 || username.length > 50) {
      setError('Username must be between 3 and 50 characters')
      return
    }
    
    if (password.length < 6) {
      setError('Password must be at least 6 characters')
      return
    }
    
    setLoading(true)

    try {
      await login(username, password, rememberMe)
      navigate('/dashboard')
    } catch (err) {
      setError('Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: `
          linear-gradient(135deg, ${alpha(theme.palette.primary.dark, 0.9)} 0%, ${alpha(theme.palette.primary.main, 0.8)} 50%, ${alpha(theme.palette.secondary.main, 0.8)} 100%),
          linear-gradient(135deg, #3B82F6 0%, #8B5CF6 50%, #EC4899 100%)
        `,
        position: 'relative',
        overflow: 'hidden',
        p: 2,
        '&::before': {
          content: '""',
          position: 'absolute',
          top: '10%',
          left: '10%',
          width: '30%',
          height: '30%',
          borderRadius: '50%',
          background: `radial-gradient(circle, ${alpha('#fff', 0.1)} 0%, transparent 70%)`,
          filter: 'blur(60px)',
        },
        '&::after': {
          content: '""',
          position: 'absolute',
          bottom: '10%',
          right: '10%',
          width: '40%',
          height: '40%',
          borderRadius: '50%',
          background: `radial-gradient(circle, ${alpha('#fff', 0.08)} 0%, transparent 70%)`,
          filter: 'blur(80px)',
        },
      }}
    >
      <Card
        sx={{
          width: '100%',
          maxWidth: 440,
          position: 'relative',
          zIndex: 1,
          backdropFilter: 'blur(20px)',
          background: alpha('#fff', 0.15),
          border: `1px solid ${alpha('#fff', 0.2)}`,
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          borderRadius: 4,
          overflow: 'visible',
        }}
      >
        {/* Logo Header */}
        <Box
          sx={{
            position: 'absolute',
            top: -40,
            left: '50%',
            transform: 'translateX(-50%)',
            width: 80,
            height: 80,
            borderRadius: 3,
            background: 'linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 10px 40px rgba(59, 130, 246, 0.4)',
            border: `4px solid ${alpha('#fff', 0.3)}`,
          }}
        >
          <VideocamIcon sx={{ fontSize: 40, color: 'white' }} />
        </Box>

        <CardContent sx={{ p: 4, pt: 6 }}>
          <Typography
            variant="h4"
            align="center"
            fontWeight={700}
            gutterBottom
            sx={{
              color: 'white',
              textShadow: '0 2px 10px rgba(0,0,0,0.1)',
            }}
          >
            FaceAttend
          </Typography>
          <Typography
            variant="body2"
            align="center"
            sx={{
              mb: 4,
              color: alpha('#fff', 0.8),
              fontWeight: 400,
            }}
          >
            Sign in to your account to continue
          </Typography>

          {error && (
            <Alert
              severity="error"
              sx={{
                mb: 3,
                borderRadius: 2,
                bgcolor: alpha('#EF4444', 0.1),
                color: '#FCA5A5',
                border: `1px solid ${alpha('#EF4444', 0.3)}`,
                '& .MuiAlert-icon': {
                  color: '#FCA5A5',
                },
              }}
            >
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              margin="normal"
              required
              autoFocus
              inputProps={{ maxLength: 50 }}
              autoComplete="username"
              sx={{
                mb: 2,
                '& .MuiOutlinedInput-root': {
                  bgcolor: alpha('#fff', 0.1),
                  borderRadius: 2,
                  color: 'white',
                  '& .MuiInputLabel-root': {
                    color: alpha('#fff', 0.7),
                  },
                  '&:hover .MuiOutlinedInput-notchedOutline': {
                    borderColor: alpha('#fff', 0.5),
                  },
                  '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                    borderColor: '#fff',
                    borderWidth: 2,
                  },
                },
                '& .MuiOutlinedInput-notchedOutline': {
                  borderColor: alpha('#fff', 0.2),
                },
              }}
            />
            <TextField
              fullWidth
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              margin="normal"
              required
              inputProps={{ minLength: 6 }}
              autoComplete="current-password"
              sx={{
                mb: 2,
                '& .MuiOutlinedInput-root': {
                  bgcolor: alpha('#fff', 0.1),
                  borderRadius: 2,
                  color: 'white',
                  '& .MuiInputLabel-root': {
                    color: alpha('#fff', 0.7),
                  },
                  '&:hover .MuiOutlinedInput-notchedOutline': {
                    borderColor: alpha('#fff', 0.5),
                  },
                  '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                    borderColor: '#fff',
                    borderWidth: 2,
                  },
                },
                '& .MuiOutlinedInput-notchedOutline': {
                  borderColor: alpha('#fff', 0.2),
                },
              }}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                      sx={{ color: alpha('#fff', 0.7) }}
                    >
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  sx={{
                    color: alpha('#fff', 0.7),
                    '&.Mui-checked': {
                      color: '#fff',
                    },
                  }}
                />
              }
              label={
                <Typography variant="body2" sx={{ color: alpha('#fff', 0.8) }}>
                  Remember me
                </Typography>
              }
              sx={{ mt: 1, mb: 2 }}
            />
            <Button
              fullWidth
              type="submit"
              variant="contained"
              size="large"
              disabled={loading}
              sx={{
                mt: 1,
                py: 1.5,
                bgcolor: 'white',
                color: theme.palette.primary.main,
                fontWeight: 600,
                borderRadius: 2,
                transition: 'all 0.3s ease',
                '&:hover': {
                  bgcolor: alpha('#fff', 0.9),
                  transform: 'translateY(-2px)',
                  boxShadow: '0 10px 30px rgba(0,0,0,0.2)',
                },
                '&:disabled': {
                  bgcolor: alpha('#fff', 0.5),
                  color: theme.palette.primary.main,
                },
              }}
            >
              {loading ? (
                <CircularProgress size={24} color="inherit" />
              ) : (
                'Sign In'
              )}
            </Button>
          </form>

          {/* Footer */}
          <Box sx={{ mt: 4, textAlign: 'center' }}>
            <Typography
              variant="caption"
              sx={{ color: alpha('#fff', 0.5) }}
            >
              Face Attendance System © {new Date().getFullYear()}
            </Typography>
          </Box>
        </CardContent>
      </Card>
    </Box>
  )
}
