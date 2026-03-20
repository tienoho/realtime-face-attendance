import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Button,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  CircularProgress,
  Alert,
} from '@mui/material'
import {
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Delete as DeleteIcon,
  Add as AddIcon,
  Videocam as VideocamIcon,
  Search as SearchIcon,
} from '@mui/icons-material'
import { camerasApi, Camera, AddCameraRequest, DiscoveredCamera } from '../api/cameras'
import { useSocket } from '../contexts/SocketContext'

interface CameraCardProps {
  camera: Camera
  onStart: () => void
  onStop: () => void
  onDelete: () => void
}

function CameraCard({ camera, onStart, onStop, onDelete }: CameraCardProps) {
  const [frame, setFrame] = useState<string | null>(null)
  const { streamCamera, stopStreamCamera, onCameraFrame } = useSocket()

  useEffect(() => {
    if (camera.connected) {
      streamCamera(camera.camera_id)
      
      const cleanup = onCameraFrame((data) => {
        if (data.camera_id === camera.camera_id) {
          setFrame(data.frame)
        }
      })
      
      return () => {
        stopStreamCamera(camera.camera_id)
        cleanup()
      }
    }
  }, [camera.connected, camera.camera_id])

  return (
    <Card>
      <Box
        sx={{
          height: 200,
          backgroundColor: '#000',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {frame ? (
          <img
            src={frame}
            alt={camera.camera_id}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <VideocamIcon sx={{ fontSize: 60, color: '#333' }} />
        )}
      </Box>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="h6">{camera.camera_id}</Typography>
          <Chip
            label={camera.connected ? 'Online' : 'Offline'}
            color={camera.connected ? 'success' : 'default'}
            size="small"
          />
        </Box>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Type: {camera.type}
        </Typography>
        {camera.stats && (
          <Typography variant="caption" color="text.secondary">
            FPS: {camera.stats.fps.toFixed(1)} | Frames: {camera.stats.frames_captured}
          </Typography>
        )}
        <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
          {camera.connected ? (
            <IconButton color="error" onClick={onStop} size="small">
              <StopIcon />
            </IconButton>
          ) : (
            <IconButton color="primary" onClick={onStart} size="small">
              <PlayIcon />
            </IconButton>
          )}
          <IconButton color="error" onClick={onDelete} size="small">
            <DeleteIcon />
          </IconButton>
        </Box>
      </CardContent>
    </Card>
  )
}

export default function Cameras() {
  const [open, setOpen] = useState(false)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [discoveredCameras, setDiscoveredCameras] = useState<DiscoveredCamera[]>([])
  const [discovering, setDiscovering] = useState(false)
  const [discoveryStatus, setDiscoveryStatus] = useState<string>('')
  const [cameraId, setCameraId] = useState('')
  const [cameraType, setCameraType] = useState<AddCameraRequest['type']>('usb')
  const [deviceIndex, setDeviceIndex] = useState(0)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['cameras'],
    queryFn: camerasApi.getCameras,
  })

  const addCameraMutation = useMutation({
    mutationFn: camerasApi.addCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
      setOpen(false)
      setCameraId('')
    },
  })

  const startCameraMutation = useMutation({
    mutationFn: camerasApi.startCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
    },
  })

  const stopCameraMutation = useMutation({
    mutationFn: camerasApi.stopCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
    },
  })

  const deleteCameraMutation = useMutation({
    mutationFn: camerasApi.removeCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
    },
  })

  const handleAddCamera = () => {
    addCameraMutation.mutate({
      camera_id: cameraId,
      type: cameraType,
      device_index: cameraType === 'usb' ? deviceIndex : undefined,
    })
  }

  const handleDiscover = async () => {
    setDiscovering(true)
    setDiscoveredCameras([])
    setDiscoveryStatus('Starting discovery...')
    try {
      // Use polling to avoid timeout
      const result = await camerasApi.discoverCamerasWithPolling(
        { scan_network: true },
        (status) => {
          setDiscoveryStatus(`Scanning: ${status}...`)
          console.log('Discovery status:', status)
        },
        60,  // max polls
        2000 // poll every 2 seconds
      )
      const allCameras = [...(result.discovered?.usb || []), ...(result.discovered?.ip || [])]
      setDiscoveredCameras(allCameras)
      setDiscoveryStatus(`Found ${allCameras.length} cameras`)
    } catch (error: any) {
      console.error('Discover error:', error)
      setDiscoveryStatus(`Error: ${error?.message || 'Unknown error'}`)
    } finally {
      setDiscovering(false)
    }
  }

  const handleAddDiscoveredCamera = (camera: DiscoveredCamera) => {
    setCameraId(camera.name.replace(/\s+/g, '_').toLowerCase())
    if (camera.type === 'usb') {
      setCameraType('usb')
      setDeviceIndex(camera.device_index || 0)
    } else {
      setCameraType(camera.type as 'rtsp' | 'http' | 'onvif')
    }
    setDiscoverOpen(false)
    setOpen(true)
  }

  const cameras = data?.cameras ? Object.values(data.cameras) : []

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" fontWeight={600}>
          Cameras
        </Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant="outlined"
            startIcon={<SearchIcon />}
            onClick={() => {
              handleDiscover()
              setDiscoverOpen(true)
            }}
          >
            Discover
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setOpen(true)}
          >
            Add Camera
          </Button>
        </Box>
      </Box>

      <Grid container spacing={3}>
        {cameras.map((camera) => (
          <Grid item xs={12} sm={6} md={4} key={camera.camera_id}>
            <CameraCard
              camera={camera}
              onStart={() => startCameraMutation.mutate(camera.camera_id)}
              onStop={() => stopCameraMutation.mutate(camera.camera_id)}
              onDelete={() => deleteCameraMutation.mutate(camera.camera_id)}
            />
          </Grid>
        ))}
        {cameras.length === 0 && (
          <Grid item xs={12}>
            <Typography color="text.secondary" align="center">
              No cameras added yet. Click "Add Camera" to get started.
            </Typography>
          </Grid>
        )}
      </Grid>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add New Camera</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Camera ID"
            fullWidth
            value={cameraId}
            onChange={(e) => setCameraId(e.target.value)}
            sx={{ mb: 2 }}
          />
          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Camera Type</InputLabel>
            <Select
              value={cameraType}
              label="Camera Type"
              onChange={(e) => setCameraType(e.target.value as AddCameraRequest['type'])}
            >
              <MenuItem value="usb">USB Camera</MenuItem>
              <MenuItem value="rtsp">RTSP Stream</MenuItem>
              <MenuItem value="http">HTTP/MJPEG</MenuItem>
              <MenuItem value="onvif">ONVIF</MenuItem>
            </Select>
          </FormControl>
          {cameraType === 'usb' && (
            <TextField
              margin="dense"
              label="Device Index"
              type="number"
              fullWidth
              value={deviceIndex}
              onChange={(e) => setDeviceIndex(Number(e.target.value))}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            onClick={handleAddCamera}
            variant="contained"
            disabled={!cameraId || addCameraMutation.isPending}
          >
            {addCameraMutation.isPending ? <CircularProgress size={20} /> : 'Add'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={discoverOpen} onClose={() => setDiscoverOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Discover Cameras</DialogTitle>
        <DialogContent>
          {discovering && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
              <CircularProgress size={24} />
              <Typography>{discoveryStatus || 'Scanning for cameras...'}</Typography>
            </Box>
          )}
          
          {!discovering && discoveredCameras.length === 0 && (
            <Alert severity="info">
              Click "Scan" to search for cameras on your network.
            </Alert>
          )}
          
          {!discovering && discoveredCameras.length > 0 && (
            <Grid container spacing={2} sx={{ mt: 1 }}>
              {discoveredCameras.map((camera, index) => (
                <Grid item xs={12} sm={6} key={index}>
                  <Card variant="outlined">
                    <CardContent sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box>
                        <Typography variant="subtitle1" fontWeight={600}>
                          {camera.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Type: {camera.type} | {camera.url}
                        </Typography>
                      </Box>
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() => handleAddDiscoveredCamera(camera)}
                      >
                        Add
                      </Button>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDiscoverOpen(false)}>Close</Button>
          <Button
            onClick={handleDiscover}
            variant="contained"
            disabled={discovering}
          >
            {discovering ? <CircularProgress size={20} /> : 'Scan'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
