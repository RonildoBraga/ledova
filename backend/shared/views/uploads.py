from django.conf import settings
from rest_framework.exceptions import APIException

from shared import upload_limits
from shared.upload_handlers import BoundedUploadHandler


class UploadRequestTooLarge(APIException):
    status_code = 413
    default_detail = "The upload request is too large."
    default_code = "upload_request_too_large"


class UploadProtectedView:
    upload_field = "file"

    def initialize_request(self, request, *args, **kwargs):
        self.upload_handler = None
        if self.action_map.get(request.method.lower()) == "create":
            self.upload_handler = BoundedUploadHandler(request, self.upload_field)
            request.upload_handlers = [self.upload_handler, *request.upload_handlers]
        return super().initialize_request(request, *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        if self.upload_handler is not None:
            try:
                declared = int(request.META.get("CONTENT_LENGTH") or 0)
            except ValueError:
                raise UploadRequestTooLarge() from None
            if declared < 0 or declared > settings.UPLOAD_MAX_REQUEST_BYTES:
                raise UploadRequestTooLarge()
        super().initial(request, *args, **kwargs)
        if self.upload_handler is not None:
            upload_limits.reserve_request(request.user.pk)
            self.upload_handler.account_for(request.user.pk)
