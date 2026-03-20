import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  Box,
  Card,
  Typography,
  Grid,
  TextField,
  Button,
  Slider,
  FormControlLabel,
  Switch,
  CircularProgress,
  Alert,
  Tabs,
  Tab,
} from '@mui/material'
import { Save as SaveIcon } from '@mui/icons-material'
import { camerasApi, StreamingConfig } from '../api/cameras'

interface TabPanelProps {
  children?: React.ReactNode
  index: number
  value: number
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  )
}

export default function Settings() {
  const [tabValue, setTabValue] = useState(0)
  const [streamingConfig, setStreamingConfig] = useState<StreamingConfig>({
    quality: 80,
    fps: 10,
    resize_width: 640,
  })
  const [successMessage, setSuccessMessage] = useState('')

  const { data: configData, isLoading: configLoading } = useQuery({
    queryKey: ['streamingConfig'],
    queryFn: camerasApi.getStreamingConfig,
  })

  useEffect(() => {
    if (configData) {
      setStreamingConfig(configData)
    }
  }, [configData])

  const updateConfigMutation = useMutation({
    mutationFn: camerasApi.updateStreamingConfig,
    onSuccess: (data) => {
      setStreamingConfig(data)
      setSuccessMessage('Settings saved successfully!')
      setTimeout(() => setSuccessMessage(''), 3000)
    },
  })

  const handleSaveStreaming = () => {
    updateConfigMutation.mutate(streamingConfig)
  }

  if (configLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h4" fontWeight={600} gutterBottom>
        Settings
      </Typography>

      {successMessage && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {successMessage}
        </Alert>
      )}

      <Card>
        <Tabs
          value={tabValue}
          onChange={(_, newValue) => setTabValue(newValue)}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Streaming" />
          <Tab label="Attendance" />
          <Tab label="Notifications" />
        </Tabs>

        <TabPanel value={tabValue} index={0}>
          <Typography variant="h6" gutterBottom>
            Streaming Configuration
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Configure the quality and performance of camera streaming
          </Typography>

          <Grid container spacing={3}>
            <Grid item xs={12}>
              <Typography gutterBottom>
                Video Quality: {streamingConfig.quality}%
              </Typography>
              <Slider
                value={streamingConfig.quality}
                onChange={(_, value) => setStreamingConfig({ ...streamingConfig, quality: value as number })}
                min={10}
                max={100}
                marks={[
                  { value: 10, label: 'Low' },
                  { value: 50, label: 'Medium' },
                  { value: 100, label: 'High' },
                ]}
              />
            </Grid>

            <Grid item xs={12}>
              <Typography gutterBottom>
                Frame Rate: {streamingConfig.fps} FPS
              </Typography>
              <Slider
                value={streamingConfig.fps}
                onChange={(_, value) => setStreamingConfig({ ...streamingConfig, fps: value as number })}
                min={1}
                max={30}
                marks={[
                  { value: 1, label: '1' },
                  { value: 15, label: '15' },
                  { value: 30, label: '30' },
                ]}
              />
            </Grid>

            <Grid item xs={12}>
              <Typography gutterBottom>
                Resolution Width: {streamingConfig.resize_width}px
              </Typography>
              <Slider
                value={streamingConfig.resize_width}
                onChange={(_, value) => setStreamingConfig({ ...streamingConfig, resize_width: value as number })}
                min={320}
                max={1920}
                step={160}
                marks={[
                  { value: 320, label: '320' },
                  { value: 640, label: '640' },
                  { value: 1280, label: '1280' },
                  { value: 1920, label: '1920' },
                ]}
              />
            </Grid>

            <Grid item xs={12}>
              <Button
                variant="contained"
                startIcon={<SaveIcon />}
                onClick={handleSaveStreaming}
                disabled={updateConfigMutation.isPending}
              >
                {updateConfigMutation.isPending ? <CircularProgress size={20} /> : 'Save Settings'}
              </Button>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          <Typography variant="h6" gutterBottom>
            Attendance Configuration
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Configure attendance recognition settings
          </Typography>

          <Grid container spacing={3}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Recognition Threshold"
                type="number"
                defaultValue={70}
                helperText="Lower values mean stricter matching (higher confidence required)"
              />
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Late Threshold (minutes)"
                type="number"
                defaultValue={15}
                helperText="Staffs arriving after this time are marked as late"
              />
            </Grid>

            <Grid item xs={12}>
              <FormControlLabel
                control={<Switch defaultChecked />}
                label="Auto-mark attendance when face recognized"
              />
            </Grid>

            <Grid item xs={12}>
              <FormControlLabel
                control={<Switch defaultChecked />}
                label="Check for duplicate attendance"
              />
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          <Typography variant="h6" gutterBottom>
            Notification Settings
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Configure email and system notifications
          </Typography>

          <Grid container spacing={3}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Email Address"
                type="email"
                placeholder="admin@example.com"
              />
            </Grid>

            <Grid item xs={12}>
              <FormControlLabel
                control={<Switch defaultChecked />}
                label="Email notifications for new staffs"
              />
            </Grid>

            <Grid item xs={12}>
              <FormControlLabel
                control={<Switch defaultChecked />}
                label="Email notifications for attendance"
              />
            </Grid>

            <Grid item xs={12}>
              <FormControlLabel
                control={<Switch />}
                label="Email notifications for system errors"
              />
            </Grid>

            <Grid item xs={12}>
              <Button variant="contained" startIcon={<SaveIcon />}>
                Save Settings
              </Button>
            </Grid>
          </Grid>
        </TabPanel>
      </Card>
    </Box>
  )
}
