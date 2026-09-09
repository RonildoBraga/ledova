from django.utils import timezone

from documents.services.retention import purge_expired_documents
from ledova_backend.procrastinate_app import app
from shared.db import use_operator


@app.periodic(cron="15 3 * * *")
@app.task
def purge_document_evidence(timestamp: int = 0):
    with use_operator():
        return purge_expired_documents(timezone.now())
