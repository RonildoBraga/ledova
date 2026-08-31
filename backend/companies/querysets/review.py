from django.db.models import QuerySet


class ApplicationReviewQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(reviewer=user)

    def with_optimized_data(self):
        return self.select_related("company", "reviewer", "assigned_by")

    def pending(self):
        from companies.models import ReviewDecision

        return self.filter(decision=ReviewDecision.PENDING)

    def completed(self):
        from companies.models import ReviewDecision

        return self.filter(decision__in=[ReviewDecision.APPROVED, ReviewDecision.REJECTED])

    def approved(self):
        from companies.models import ReviewDecision

        return self.filter(decision=ReviewDecision.APPROVED)

    def rejected(self):
        from companies.models import ReviewDecision

        return self.filter(decision=ReviewDecision.REJECTED)

    def for_company(self, company):
        return self.filter(company=company).order_by("review_order")


class ReviewNoteQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(visible_to_company=True)

    def with_optimized_data(self):
        return self.select_related("review", "review__company", "author")

    def internal_only(self):
        return self.filter(visible_to_company=False)

    def external(self):
        return self.filter(visible_to_company=True)
