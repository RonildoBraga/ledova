import uuid

from django.db import models


class BaseModel(models.Model):
    """
    Base model that provides common fields for all models in the application.

    Includes:
    - uuid: Primary key - a unique identifier for the model (instead of auto-incrementing id)
    - created_at: Automatically set when the object is created
    - updated_at: Automatically updated when the object is saved

    Benefits of UUID as primary key:
    - Better for distributed systems and microservices
    - No sequential IDs that could leak information
    - More secure for public-facing identifiers
    - Better for API design
    """

    uuid = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, help_text="Unique identifier (primary key)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
