import logging
import subprocess
import shutil
from typing import Tuple

import cv2

logger = logging.getLogger(__name__)


class PiCameraStream:
    """Gestion de la caméra Raspberry Pi via Picamera2 avec repli OpenCV."""

    def __init__(self) -> None:
        self.backend = None  # 'picamera2' ou 'opencv'
        self.picam2 = None
        self.cap = None
        self.still_config = None

    def open(
        self,
        resolution: Tuple[int, int] = (1280, 720),
        framerate: int = 30,
        rotate: int = 0,
        hflip: bool = False,
        vflip: bool = False,
    ) -> bool:
        """Ouvre la caméra avec les paramètres donnés."""
        try:
            from picamera2 import Picamera2
            from libcamera import Transform, controls

            self.backend = "picamera2"
            self.picam2 = Picamera2()
            transform = Transform(rotation=rotate, hflip=hflip, vflip=vflip)
            config = self.picam2.create_preview_configuration(
                main={"size": resolution, "format": "BGR888"},
                transform=transform,
            )
            self.picam2.configure(config)
            try:
                self.picam2.set_controls({"FrameRate": framerate})
            except Exception:
                pass
            try:
                self.picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
            except Exception:
                pass
            self.picam2.start()
            self.still_config = self.picam2.create_still_configuration(transform=transform)
            return True
        except Exception as e:
            logger.warning(
                "Picamera2 indisponible (%s). Installez python3-picamera2 via apt.",
                e,
            )

        # Fallback OpenCV
        self.backend = "opencv"
        # Le backend V4L2 est recommandé pour les caméras Pi via OpenCV
        self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            logger.error("Impossible d'ouvrir la caméra via OpenCV")
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        self.cap.set(cv2.CAP_PROP_FPS, framerate)
        return True

    def get_frame(self):
        """Retourne une frame BGR ou None en cas d'erreur."""
        if self.backend == "picamera2" and self.picam2:
            try:
                return self.picam2.capture_array("main")
            except Exception as e:
                logger.error("Erreur capture Picamera2: %s", e)
                return None
        elif self.backend == "opencv" and self.cap:
            ret, frame = self.cap.read()
            if ret:
                return frame
            return None
        return None

    def capture_photo(self, path: str) -> None:
        """Capture une photo pleine résolution et l'enregistre."""
        if self.backend == "picamera2" and self.picam2:
            try:
                if self.still_config:
                    self.picam2.switch_mode_and_capture_file(self.still_config, path)
                else:
                    self.picam2.capture_file(path)
            except Exception as e:
                logger.error("Erreur capture photo Picamera2: %s", e)
                raise
        elif self.backend == "opencv" and self.cap:
            # Si les utilitaires libcamera sont disponibles, utiliser libcamera-still
            libcamera_still = shutil.which("libcamera-still")
            if libcamera_still:
                try:
                    subprocess.run(
                        [libcamera_still, "-o", path, "--immediate"],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    return
                except subprocess.CalledProcessError as e:
                    logger.error(
                        "libcamera-still a échoué (%s), repli sur OpenCV pour la capture", e
                    )
            ret, frame = self.cap.read()
            if not ret:
                raise RuntimeError("Impossible de capturer une image")
            cv2.imwrite(path, frame)
        else:
            raise RuntimeError("Caméra non initialisée")

    def close(self) -> None:
        """Ferme la caméra et libère les ressources."""
        if self.backend == "picamera2" and self.picam2:
            try:
                self.picam2.stop()
            except Exception:
                pass
            self.picam2.close()
            self.picam2 = None
        elif self.backend == "opencv" and self.cap:
            self.cap.release()
            self.cap = None
        self.backend = None
