"""
Data Augmentation Module
========================

Applies various augmentations to face images to improve model robustness.
"""

import cv2
import numpy as np
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class DataAugmentor:
    """
    Data augmentation for face images.
    
    Augmentations:
    - Horizontal flip
    - Rotation (±15°, ±30°)
    - Brightness adjustment
    - Contrast adjustment
    - Slight translation
    """
    
    def __init__(
        self,
        rotation_angles: List[int] = None,
        brightness_range: Tuple[float, float] = (0.7, 1.3),
        contrast_range: Tuple[float, float] = (0.8, 1.2),
        flip_probability: float = 0.5
    ):
        """
        Initialize the augmentor.
        
        Args:
            rotation_angles: List of rotation angles to apply
            brightness_range: (min, max) brightness multiplier
            contrast_range: (min, max) contrast multiplier
            flip_probability: Probability of horizontal flip
        """
        self.rotation_angles = rotation_angles or [-30, -15, 15, 30]
        self.brightness_range = brightness_range
        self.contrast_range = contrast_range
        self.flip_probability = flip_probability
    
    def rotate_image(
        self, 
        image: np.ndarray, 
        angle: float,
        center: Tuple[int, int] = None
    ) -> np.ndarray:
        """
        Rotate image by specified angle.
        
        Args:
            image: Input image
            angle: Rotation angle in degrees (positive = counter-clockwise)
            center: Rotation center (default: image center)
            
        Returns:
            Rotated image
        """
        # Validate input
        if image is None or image.size == 0:
            logger.debug("rotate_image skipped: empty image")
            return image
        if len(image.shape) < 2:
            logger.debug("rotate_image skipped: invalid shape")
            return image
        
        h, w = image.shape[:2]
        if center is None:
            center = (w // 2, h // 2)
        
        # Get rotation matrix
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Compute bounding box
        cos = np.abs(matrix[0, 0])
        sin = np.abs(matrix[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        
        # Adjust rotation matrix for translation
        matrix[0, 2] += (new_w / 2) - center[0]
        matrix[1, 2] += (new_h / 2) - center[1]
        
        # Apply rotation
        return cv2.warpAffine(
            image, 
            matrix, 
            (new_w, new_h),
            borderMode=cv2.BORDER_REFLECT
        )
    
    def adjust_brightness(
        self, 
        image: np.ndarray, 
        factor: float
    ) -> np.ndarray:
        """
        Adjust image brightness.
        
        Args:
            image: Input image
            factor: Brightness factor (1.0 = no change)
            
        Returns:
            Brightness-adjusted image
        """
        # Validate input - must be color image
        if image is None or image.size == 0:
            logger.debug("adjust_brightness skipped: empty image")
            return image
        if len(image.shape) != 3 or image.shape[2] != 3:
            logger.debug("adjust_brightness skipped: not a color image")
            return image
        
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hsv = hsv.astype(np.float32)
        hsv[:, :, 2] = hsv[:, :, 2] * factor
        hsv[:, :, 2] = np.clip(hsv[:, :, 2], 0, 255)
        hsv = hsv.astype(np.uint8)
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    
    def adjust_contrast(
        self, 
        image: np.ndarray, 
        factor: float
    ) -> np.ndarray:
        """
        Adjust image contrast.
        
        Args:
            image: Input image
            factor: Contrast factor (1.0 = no change)
            
        Returns:
            Contrast-adjusted image
        """
        # Validate input - must be color image
        if image is None or image.size == 0:
            logger.debug("adjust_contrast skipped: empty image")
            return image
        if len(image.shape) != 3 or image.shape[2] != 3:
            logger.debug("adjust_contrast skipped: not a color image")
            return image
        
        # Convert to LAB color space
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        
        # Apply contrast adjustment to L channel
        l_channel = l_channel.astype(np.float32)
        l_channel = ((l_channel - 128) * factor) + 128
        l_channel = np.clip(l_channel, 0, 255).astype(np.uint8)
        
        # Merge and convert back
        lab = cv2.merge([l_channel, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    def flip_horizontal(self, image: np.ndarray) -> np.ndarray:
        """Flip image horizontally."""
        return cv2.flip(image, 1)
    
    def translate_image(
        self, 
        image: np.ndarray, 
        tx: int, 
        ty: int
    ) -> np.ndarray:
        """
        Translate image by (tx, ty) pixels.
        
        Args:
            image: Input image
            tx: Translation in x direction
            ty: Translation in y direction
            
        Returns:
            Translated image
        """
        # Validate input
        if image is None or image.size == 0:
            logger.debug("translate_image skipped: empty image")
            return image
        if len(image.shape) < 2:
            logger.debug("translate_image skipped: invalid shape")
            return image
        
        matrix = np.float32([[1, 0, tx], [0, 1, ty]])
        return cv2.warpAffine(
            image, 
            matrix, 
            (image.shape[1], image.shape[0]),
            borderMode=cv2.BORDER_REFLECT
        )
    
    def augment(
        self, 
        image: np.ndarray,
        num_augmentations: int = 5,
        random_seed: int = None
    ) -> List[np.ndarray]:
        """
        Generate augmented versions of an image.
        
        Args:
            image: Input image
            num_augmentations: Number of augmented images to generate
            random_seed: Random seed for reproducibility
            
        Returns:
            List of augmented images
        """
        if random_seed is not None:
            np.random.seed(random_seed)
        
        augmented = [image.copy()]  # Original image
        
        # Generate random augmentations
        for _ in range(num_augmentations):
            aug_img = image.copy()
            
            # Random rotation
            if np.random.random() < 0.7:
                angle = np.random.choice(self.rotation_angles)
                aug_img = self.rotate_image(aug_img, angle)
            
            # Random brightness
            if np.random.random() < 0.7:
                factor = np.random.uniform(*self.brightness_range)
                aug_img = self.adjust_brightness(aug_img, factor)
            
            # Random contrast
            if np.random.random() < 0.7:
                factor = np.random.uniform(*self.contrast_range)
                aug_img = self.adjust_contrast(aug_img, factor)
            
            # Random flip
            if np.random.random() < self.flip_probability:
                aug_img = self.flip_horizontal(aug_img)
            
            # Random translation
            if np.random.random() < 0.5:
                h, w = aug_img.shape[:2]
                tx = np.random.randint(-w//10, w//10)
                ty = np.random.randint(-h//10, h//10)
                aug_img = self.translate_image(aug_img, tx, ty)
            
            augmented.append(aug_img)
        
        return augmented
    
    def augment_single(
        self,
        image: np.ndarray,
        rotation: bool = True,
        brightness: bool = True,
        contrast: bool = True,
        flip: bool = False
    ) -> np.ndarray:
        """
        Apply a single deterministic augmentation.
        
        Args:
            image: Input image
            rotation: Apply rotation (±15°)
            brightness: Adjust brightness (0.9-1.1)
            contrast: Adjust contrast (0.9-1.1)
            flip: Apply horizontal flip
            
        Returns:
            Augmented image
        """
        aug_img = image.copy()
        
        if rotation:
            angle = np.random.choice([-15, 15])
            aug_img = self.rotate_image(aug_img, angle)
        
        if brightness:
            factor = np.random.uniform(0.9, 1.1)
            aug_img = self.adjust_brightness(aug_img, factor)
        
        if contrast:
            factor = np.random.uniform(0.9, 1.1)
            aug_img = self.adjust_contrast(aug_img, factor)
        
        if flip:
            aug_img = self.flip_horizontal(aug_img)
        
        return aug_img


def augment_face_batch(
    images: List[np.ndarray],
    target_count: int = 10,
    augmentor: DataAugmentor = None
) -> List[np.ndarray]:
    """
    Augment a batch of face images to reach target count.
    
    Args:
        images: List of input face images
        target_count: Target number of images
        augmentor: DataAugmentor instance
        
    Returns:
        List of augmented images (at least target_count)
    """
    if augmentor is None:
        augmentor = DataAugmentor()
    
    result = list(images)
    
    # If we already have enough, just return subset
    if len(result) >= target_count:
        return result[:target_count]
    
    # Calculate how many more we need
    needed = target_count - len(result)
    
    # Generate augmentations from existing images
    for img in images:
        if len(result) >= target_count:
            break
        
        # Create a few variations of this image
        variations = augmentor.augment(img, num_augmentations=3)
        for var in variations[1:]:  # Skip original
            if len(result) >= target_count:
                break
            result.append(var)
    
    return result


def test_augmentor():
    """Quick test of the augmentor."""
    import os
    
    print("Testing DataAugmentor...")
    
    augmentor = DataAugmentor()
    
    # Create a test image (color)
    test_image = np.zeros((200, 200, 3), dtype=np.uint8)
    test_image[:, :] = [128, 128, 128]  # Gray
    
    # Add a rectangle to see transformations
    cv2.rectangle(test_image, (50, 50), (150, 150), (255, 0, 0), -1)
    
    # Test single augmentation
    aug = augmentor.augment_single(test_image, rotation=True, brightness=True)
    print(f"✓ Single augmentation works, shape: {aug.shape}")
    
    # Test batch augmentation
    augmented = augmentor.augment(test_image, num_augmentations=5)
    print(f"✓ Batch augmentation works: {len(augmented)} images")
    
    # Test face batch augmentation
    faces = [test_image.copy() for _ in range(3)]
    result = augment_face_batch(faces, target_count=10)
    print(f"✓ Face batch augmentation: {len(result)} images")
    
    return True


if __name__ == "__main__":
    test_augmentor()
