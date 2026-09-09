from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from rest_framework import serializers
from rest_framework.exceptions import APIException

from shared import upload_limits
from shared.uploads import upload_size_error


class BoundedUploadHandler(FileUploadHandler):
    def __init__(self, request, field):
        super().__init__(request)
        self.field = field
        self.file_count = 0
        self.bytes_received = 0
        self.user_id = None
        self.error = None

    def refuse(self, error):
        self.error = error
        raise StopUpload(connection_reset=True)

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.file_count += 1
        if self.file_count > 1:
            self.refuse(serializers.ValidationError({self.field: ["Upload one file at a time."]}))

    def receive_data_chunk(self, raw_data, start):
        self.bytes_received += len(raw_data)
        if self.user_id is not None:
            try:
                upload_limits.reserve_bytes(self.user_id, len(raw_data))
            except APIException as error:
                self.refuse(error)
        if self.bytes_received > settings.UPLOAD_MAX_BYTES:
            self.refuse(serializers.ValidationError({self.field: [upload_size_error()]}))
        return raw_data

    def file_complete(self, file_size):
        return None

    def upload_complete(self):
        if self.error is not None:
            raise self.error

    def account_for(self, user_id):
        upload_limits.reserve_bytes(user_id, self.bytes_received)
        self.user_id = user_id
