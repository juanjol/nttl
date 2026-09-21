class CameraError(Exception):
    pass


class CameraNotFoundError(CameraError):
    pass


class CameraNotOpenError(CameraError):
    pass


class CameraBusyError(CameraError):
    pass


class ExposureFailedError(CameraError):
    pass


class ControlNotSupportedError(CameraError):
    pass


class InvalidRoiError(CameraError):
    pass


class SdkNotAvailableError(CameraError):
    pass
