import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  Box,
  Drawer,
  AppBar,
  Toolbar,
  List,
  Typography,
  Divider,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Avatar,
  Menu,
  MenuItem,
  useTheme,
  alpha,
} from '@mui/material'
import {
  Dashboard as DashboardIcon,
  Videocam as VideocamIcon,
  People as PeopleIcon,
  Assessment as AssessmentIcon,
  Settings as SettingsIcon,
  Menu as MenuIcon,
  Logout as LogoutIcon,
  Person as PersonIcon,
  Notifications as NotificationsIcon,
} from '@mui/icons-material'
import { useAuth } from '../../contexts/AuthContext'

const drawerWidth = 260

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/dashboard' },
  { text: 'Cameras', icon: <VideocamIcon />, path: '/cameras' },
  { text: 'Students', icon: <PeopleIcon />, path: '/students' },
  { text: 'Reports', icon: <AssessmentIcon />, path: '/reports' },
  { text: 'Settings', icon: <SettingsIcon />, path: '/settings' },
]

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const theme = useTheme()

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
  }

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleClose = () => {
    setAnchorEl(null)
  }

  const handleLogout = () => {
    handleClose()
    logout()
    navigate('/login')
  }

  // Active menu item check
  const isActive = (path: string) => location.pathname === path

  const drawer = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Sidebar Header */}
      <Box
        sx={{
          p: 3,
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.primary.dark} 100%)`,
        }}
      >
        <Box
          sx={{
            width: 40,
            height: 40,
            borderRadius: 2,
            bgcolor: 'white',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <VideocamIcon sx={{ color: theme.palette.primary.main, fontSize: 24 }} />
        </Box>
        <Typography
          variant="h6"
          sx={{
            fontWeight: 700,
            color: 'white',
            letterSpacing: '-0.02em',
          }}
        >
          FaceAttend
        </Typography>
      </Box>

      <Divider />

      {/* Navigation */}
      <List sx={{ px: 2, py: 2, flexGrow: 1 }}>
        {menuItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={{ mb: 0.5 }}>
            <ListItemButton
              selected={isActive(item.path)}
              onClick={() => navigate(item.path)}
              sx={{
                borderRadius: 2,
                py: 1.5,
                position: 'relative',
                overflow: 'hidden',
                '&.Mui-selected': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.12),
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    left: 0,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: 4,
                    height: '60%',
                    borderRadius: 4,
                    backgroundColor: theme.palette.primary.main,
                  },
                  '& .MuiListItemIcon-root': {
                    color: theme.palette.primary.main,
                  },
                  '& .MuiListItemText-primary': {
                    fontWeight: 600,
                    color: theme.palette.primary.main,
                  },
                },
                '&:hover': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.08),
                },
              }}
            >
              <ListItemIcon
                sx={{
                  minWidth: 40,
                  color: theme.palette.text.secondary,
                }}
              >
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.text}
                primaryTypographyProps={{
                  fontSize: '0.9rem',
                  fontWeight: 500,
                }}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>

      {/* User Info at Bottom */}
      <Divider />
      <Box sx={{ p: 2 }}>
        <Box
          sx={{
            p: 2,
            borderRadius: 2,
            bgcolor: alpha(theme.palette.primary.main, 0.08),
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
          }}
        >
          <Avatar
            sx={{
              width: 36,
              height: 36,
              bgcolor: theme.palette.primary.main,
              fontSize: '0.9rem',
              fontWeight: 600,
            }}
          >
            {user?.username?.charAt(0).toUpperCase() || 'U'}
          </Avatar>
          <Box sx={{ overflow: 'hidden' }}>
            <Typography
              variant="body2"
              fontWeight={600}
              noWrap
              sx={{ fontSize: '0.85rem' }}
            >
              {user?.username || 'User'}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              noWrap
              sx={{ fontSize: '0.7rem' }}
            >
              Administrator
            </Typography>
          </Box>
        </Box>
      </Box>
    </Box>
  )

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {/* App Bar */}
      <AppBar
        position="fixed"
        elevation={0}
        sx={{
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
          bgcolor: 'background.paper',
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Toolbar sx={{ minHeight: { xs: 64 } }}>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{
              mr: 2,
              display: { md: 'none' },
              color: 'text.primary',
            }}
          >
            <MenuIcon />
          </IconButton>

          {/* Page Title */}
          <Box sx={{ flexGrow: 1 }}>
            <Typography
              variant="h5"
              sx={{
                fontWeight: 700,
                color: 'text.primary',
                display: { xs: 'none', sm: 'block' },
              }}
            >
              {menuItems.find((item) => item.path === location.pathname)?.text || 'Dashboard'}
            </Typography>
          </Box>

          {/* Right Side Actions */}
          <IconButton sx={{ mr: 1 }}>
            <NotificationsIcon sx={{ color: 'text.secondary' }} />
          </IconButton>

          <IconButton onClick={handleMenu} sx={{ p: 0.5 }}>
            <Avatar
              sx={{
                width: 36,
                height: 36,
                bgcolor: 'primary.main',
                fontSize: '0.9rem',
              }}
            >
              {user?.username?.charAt(0).toUpperCase() || 'U'}
            </Avatar>
          </IconButton>

          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={handleClose}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'right',
            }}
            transformOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
            PaperProps={{
              sx: {
                mt: 1,
                minWidth: 180,
                borderRadius: 2,
                boxShadow: '0 10px 40px rgba(0,0,0,0.1)',
              },
            }}
          >
            <Box sx={{ px: 2, py: 1.5, borderBottom: `1px solid ${theme.palette.divider}` }}>
              <Typography variant="body2" fontWeight={600}>
                {user?.username}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                admin@faceattend.com
              </Typography>
            </Box>
            <MenuItem onClick={handleClose}>
              <ListItemIcon>
                <PersonIcon fontSize="small" />
              </ListItemIcon>
              Profile
            </MenuItem>
            <MenuItem onClick={handleLogout}>
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              Logout
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      {/* Sidebar - Permanent on Desktop */}
      <Box
        component="nav"
        sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}
      >
        {/* Mobile Drawer */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: drawerWidth,
              borderRight: 'none',
            },
          }}
        >
          {drawer}
        </Drawer>

        {/* Desktop Drawer */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: drawerWidth,
              borderRight: 'none',
              boxShadow: '4px 0 20px rgba(0,0,0,0.05)',
            },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      {/* Main Content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { md: `calc(100% - ${drawerWidth}px)` },
          mt: '64px',
          bgcolor: 'background.default',
          minHeight: 'calc(100vh - 64px)',
        }}
      >
        <Outlet />
      </Box>
    </Box>
  )
}
