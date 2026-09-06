from django.db.models import Q, QuerySet, Sum

from tokens.models.choices import RequestStatus


class ShareIssuanceRequestQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.visible_to_user(user)
        return self.filter(token__company__in=user_companies)

    def manageable_by_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.manageable_by_user(user)
        return self.filter(token__company__in=user_companies)

    def unminted(self, token):
        from tokens.models import ShareIssuance

        return self.filter(token=token).filter(
            Q(status__in=(RequestStatus.APPROVED, RequestStatus.EXECUTING))
            | Q(status=RequestStatus.FAILED, uuid__in=ShareIssuance.objects.unconfirmed_request_uuids())
        )

    def share_total(self) -> int:
        return int(self.aggregate(total=Sum("amount"))["total"] or 0)

    def unresolved_on_chain(self, cutoff):
        from tokens.models import ShareIssuance

        return self.filter(updated_at__lt=cutoff).filter(
            Q(status=RequestStatus.EXECUTING)
            | Q(status=RequestStatus.FAILED, uuid__in=ShareIssuance.objects.unconfirmed_request_uuids())
        )
