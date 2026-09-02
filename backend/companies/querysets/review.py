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


class ReviewNoteQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(visible_to_company=True)

    def with_optimized_data(self):
        return self.select_related("review", "review__company", "author")
