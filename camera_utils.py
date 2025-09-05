import cv2
import threading
import time
import logging

logger = logging.getLogger(__name__)


class PiCamera:
    """Gestion de la caméra Raspberry Pi avec différents backends."""

    def __init__(self, resolution=(1280, 720), framerate=30):
        self.resolution = resolution
        self.framerate = framerate
        self.frame = None
        self.lock = threading.Lock()
        self.is_running = False
        self.thread = None
        self.backend = None  # 'picamera', 'picamera2' ou 'opencv'
        self.camera = None   # objet caméra selon le backend

    def start(self):
        """Initialise la caméra Pi en testant plusieurs bibliothèques."""
        # Essayer d'abord la bibliothèque picamera (ancienne)
        try:
            import picamera
            import picamera.array
            self.backend = 'picamera'
            self.camera = picamera.PiCamera()
            self.camera.resolution = self.resolution
            self.camera.framerate = self.framerate
            self._raw_capture = picamera.array.PiRGBArray(self.camera, size=self.resolution)
            self.is_running = True
            self.thread = threading.Thread(target=self._capture_loop_picamera)
            self.thread.daemon = True
            self.thread.start()
            logger.info("[PI CAMERA] Caméra initialisée via picamera")
            return True
        except Exception as e:
            logger.info(f"[PI CAMERA] picamera indisponible: {e}")

        # Essayer ensuite picamera2
        try:
            from picamera2 import Picamera2
            self.backend = 'picamera2'
            self.camera = Picamera2()
            config = self.camera.create_preview_configuration(main={"size": self.resolution})
            self.camera.configure(config)
            self.camera.start()
            self.is_running = True
            self.thread = threading.Thread(target=self._capture_loop_picamera2)
            self.thread.daemon = True
            self.thread.start()
            logger.info("[PI CAMERA] Caméra initialisée via picamera2")
            return True
        except Exception as e:
            logger.info(f"[PI CAMERA] picamera2 indisponible: {e}")

        # Enfin, essayer OpenCV avec différents backends
        try:
            self.backend = 'opencv'
            backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
            for backend in backends:
                backend_name = 'V4L2' if backend == cv2.CAP_V4L2 else 'AUTO'
                logger.info(f"[PI CAMERA] Tentative d'ouverture via OpenCV backend {backend_name}...")
                try:
                    self.camera = cv2.VideoCapture(0, backend)
                    if not self.camera.isOpened():
                        logger.info(f"[PI CAMERA] Backend {backend_name} : échec d'ouverture")
                        if self.camera:
                            self.camera.release()
                        continue
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
                    self.camera.set(cv2.CAP_PROP_FPS, self.framerate)
                    self.is_running = True
                    self.thread = threading.Thread(target=self._capture_loop_opencv)
                    self.thread.daemon = True
                    self.thread.start()
                    logger.info(f"[PI CAMERA] Caméra initialisée via OpenCV backend {backend_name}")
                    return True
                except Exception as e_backend:
                    logger.info(f"[PI CAMERA] Erreur backend {backend_name}: {e_backend}")
                    if self.camera:
                        self.camera.release()
                    self.camera = None
                    continue
            raise RuntimeError("Impossible d'ouvrir la caméra Pi avec OpenCV")
        except Exception as e:
            logger.info(f"[PI CAMERA] Erreur initialisation OpenCV: {e}")
            self.camera = None
            return False

    def _capture_loop_picamera(self):
        import numpy as np  # utilisé pour conversion
        for frame in self.camera.capture_continuous(self._raw_capture, format='bgr', use_video_port=True):
            image = frame.array
            _, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            with self.lock:
                self.frame = jpeg.tobytes()
            self._raw_capture.truncate(0)
            if not self.is_running:
                break

    def _capture_loop_picamera2(self):
        while self.is_running:
            try:
                image = self.camera.capture_array()
                _, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                with self.lock:
                    self.frame = jpeg.tobytes()
            except Exception as e:
                logger.info(f"[PI CAMERA] Erreur capture picamera2: {e}")
            time.sleep(0.03)

    def _capture_loop_opencv(self):
        while self.is_running:
            ret, image = self.camera.read()
            if ret:
                _, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                with self.lock:
                    self.frame = jpeg.tobytes()
            else:
                logger.info("[PI CAMERA] Erreur de lecture de frame")
            time.sleep(0.03)

    def get_frame(self):
        with self.lock:
            return self.frame

    def capture_photo(self, filepath):
        """Capture une photo et la sauvegarde au chemin indiqué."""
        if self.backend == 'picamera':
            self.camera.capture(filepath, format='jpeg')
        elif self.backend == 'picamera2':
            self.camera.capture_file(filepath)
        elif self.backend == 'opencv':
            ret, image = self.camera.read()
            if not ret:
                raise RuntimeError("Impossible de capturer une image")
            cv2.imwrite(filepath, image)
        else:
            raise RuntimeError("Caméra Pi non initialisée")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        try:
            if self.backend == 'picamera' and self.camera:
                self.camera.close()
            elif self.backend == 'picamera2' and self.camera:
                try:
                    self.camera.stop()
                except Exception:
                    pass
                self.camera.close()
            elif self.backend == 'opencv' and self.camera:
                self.camera.release()
        finally:
            self.camera = None
        logger.info("[PI CAMERA] Caméra arrêtée")

