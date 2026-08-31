from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from companies.models import Company, CompanyStatus


class Command(BaseCommand):
    help = "Generate a report of company application statuses"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pending-only",
            action="store_true",
            help="Show only pending applications (submitted, review, info_required)",
        )
        parser.add_argument(
            "--detailed",
            action="store_true",
            help="Show detailed list of companies in each status",
        )

    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.WARNING("COMPANY APPLICATION STATUS REPORT"))
        self.stdout.write(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        self.stdout.write("=" * 60 + "\n")

        pending_only = options.get("pending_only")
        detailed = options.get("detailed")

        status_counts = Company.objects.values("status").annotate(count=Count("id")).order_by("status")

        pending_statuses = [
            CompanyStatus.DRAFT,
            CompanyStatus.SUBMITTED,
            CompanyStatus.REVIEW,
            CompanyStatus.INFO_REQUIRED,
        ]

        if pending_only:
            status_counts = [s for s in status_counts if s["status"] in pending_statuses]

        self.stdout.write(self.style.HTTP_INFO("STATUS SUMMARY:"))
        self.stdout.write("-" * 40)

        total = 0
        for status_data in status_counts:
            status = status_data["status"]
            count = status_data["count"]
            total += count

            label = dict(CompanyStatus.choices).get(status, status)

            if status in [CompanyStatus.ACTIVE]:
                style = self.style.SUCCESS
            elif status in [CompanyStatus.APPROVED]:
                style = self.style.HTTP_SUCCESS
            elif status in [CompanyStatus.SUBMITTED, CompanyStatus.REVIEW]:
                style = self.style.WARNING
            elif status in [CompanyStatus.REJECTED, CompanyStatus.SUSPENDED, CompanyStatus.DELISTED]:
                style = self.style.ERROR
            else:
                style = self.style.HTTP_INFO

            self.stdout.write(f"  {style(f'{label}:')} {count}")

        self.stdout.write("-" * 40)
        self.stdout.write(f"  Total: {total}\n")

        if detailed:
            self.stdout.write(self.style.HTTP_INFO("\nDETAILED BREAKDOWN:"))

            for status_data in status_counts:
                status = status_data["status"]
                label = dict(CompanyStatus.choices).get(status, status)
                companies = Company.objects.filter(status=status).order_by("-created_at")[:10]

                if companies.exists():
                    self.stdout.write(f"\n{label}:")
                    self.stdout.write("-" * 40)
                    for company in companies:
                        self.stdout.write(
                            f"  - {company.name} (ACN: {company.acn}) - "
                            f"Created: {company.created_at.strftime('%Y-%m-%d')}"
                        )
                    if status_data["count"] > 10:
                        self.stdout.write(f"  ... and {status_data['count'] - 10} more")

        pending_review = Company.objects.filter(status__in=[CompanyStatus.SUBMITTED, CompanyStatus.REVIEW]).count()

        if pending_review > 0:
            self.stdout.write(self.style.WARNING(f"\n⚠ {pending_review} application(s) pending review action"))

        self.stdout.write("\n" + "=" * 60 + "\n")
