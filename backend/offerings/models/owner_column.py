from django.db import models


class DerivesCompanyFromToken(models.Model):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.company_id is None and self.token_id is not None:
            self.company_id = self.token.company_id
        super().save(*args, **kwargs)


class DerivesCompanyFromOffering(models.Model):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.company_id is None and self.offering_id is not None:
            self.company_id = self.offering.company_id
        super().save(*args, **kwargs)
