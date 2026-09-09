from rest_framework.exceptions import APIException


class UploadUnavailable(APIException):
    status_code = 503
    default_detail = "Uploads are temporarily unavailable. Please try again later."
    default_code = "upload_unavailable"


class UploadRejected(Exception):
    pass
