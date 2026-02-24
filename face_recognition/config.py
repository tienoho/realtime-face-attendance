"""
Face Recognition Configuration
============================

Configuration constants for the face recognition pipeline.
"""

# ============================================================
# DETECTOR CONFIGURATION
# ============================================================

# InsightFace model selection
# 'buffalo_s' - Smaller, faster, slightly less accurate
# 'buffalo_l' - Larger, slower, more accurate
DETECTOR_MODEL = 'buffalo_s'

# Detection input size (width, height)
# Smaller = faster but may miss small faces
DETECTOR_SIZE = (320, 320)

# Detection confidence threshold (0.0 - 1.0)
DETECTOR_THRESHOLD = 0.5

# ============================================================
# EMBEDDING CONFIGURATION
# ============================================================

# Embedding dimension (InsightFace buffalo_s/l output)
EMBEDDING_DIM = 512

# ============================================================
# RECOGNITION CONFIGURATION
# ============================================================

# Recognition similarity threshold (0.0 - 1.0)
# Higher = more strict matching
RECOGNITION_THRESHOLD = 0.6

# ============================================================
# VECTOR STORE CONFIGURATION
# ============================================================

# Path to FAISS index file
INDEX_PATH = 'models/faiss_index.bin'

# Use GPU for FAISS search (if available)
USE_GPU = False

# Number of clusters for IVF index (for large datasets)
IVF_NLIST = 100

# Number of clusters to search
IVF_NPROBE = 10

# ============================================================
# ATTENDANCE CONFIGURATION
# ============================================================

# Cooldown between attendance records (seconds)
# Prevents duplicate attendance in same time window
ATTENDANCE_COOLDOWN = 300  # 5 minutes

# ============================================================
# AUGMENTATION CONFIGURATION
# ============================================================

# Rotation angles to apply
AUGMENTATION_ROTATION_ANGLES = [-30, -15, 15, 30]

# Brightness adjustment range (min, max) multiplier
AUGMENTATION_BRIGHTNESS_RANGE = (0.7, 1.3)

# Contrast adjustment range (min, max) multiplier
AUGMENTATION_CONTRAST_RANGE = (0.8, 1.2)

# Probability of horizontal flip
AUGMENTATION_FLIP_PROBABILITY = 0.5

# Target number of augmented images per registration
AUGMENTATION_TARGET_COUNT = 10
