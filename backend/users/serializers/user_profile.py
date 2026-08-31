from rest_framework import serializers

from shared.models.country import Country
from users.models.user_profile import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    uuid = serializers.CharField(read_only=True)
    citizenship_country = serializers.PrimaryKeyRelatedField(queryset=Country.objects.none())
    citizenship_country_name = serializers.SerializerMethodField()
    residence_country = serializers.PrimaryKeyRelatedField(queryset=Country.objects.none(), required=False)
    residence_country_name = serializers.SerializerMethodField()
    email = serializers.EmailField(required=False)
    is_active = serializers.SerializerMethodField()
    is_staff = serializers.SerializerMethodField()
    date_joined = serializers.SerializerMethodField()
    last_login = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = (
            "uuid",
            "full_name",
            "email",
            "is_active",
            "is_staff",
            "date_joined",
            "last_login",
            "phone_country_code",
            "phone_number",
            "date_of_birth",
            "residential_address",
            "citizenship_country",
            "citizenship_country_name",
            "residence_country",
            "residence_country_name",
            "confirmed_over_18",
            "confirmed_australian_resident",
            "confirmed_individual_account",
            "pre_screening_completed_at",
            "is_id_verified",
            "terms_and_conditions",
            "is_signup_completed",
            "kyc_provider",
            "verification_status",
            "review_result",
            "rejection_labels",
            "verified_at",
            "kycaid_applicant_id",
            "sumsub_applicant_id",
            "sumsub_verification_status",
            "sumsub_review_result",
            "sumsub_review_answer",
            "sumsub_rejection_labels",
            "sumsub_verified_at",
        )
        read_only_fields = (
            "uuid",
            "is_id_verified",
            "residence_country",
            "pre_screening_completed_at",
            "kyc_provider",
            "verification_status",
            "review_result",
            "rejection_labels",
            "verified_at",
            "kycaid_applicant_id",
            "sumsub_applicant_id",
            "sumsub_verification_status",
            "sumsub_review_result",
            "sumsub_review_answer",
            "sumsub_rejection_labels",
            "sumsub_verified_at",
        )

    def get_is_active(self, obj):
        """Get is_active status from the related user."""
        return obj.user.is_active if obj.user else None

    def get_is_staff(self, obj):
        """Get is_staff status from the related user."""
        return obj.user.is_staff if obj.user else None

    def get_date_joined(self, obj):
        """Get date_joined from the related user."""
        return obj.user.date_joined if obj.user else None

    def get_last_login(self, obj):
        """Get last_login from the related user."""
        return obj.user.last_login if obj.user else None

    def get_citizenship_country_name(self, obj):
        """Get the name of the citizenship country."""
        return obj.citizenship_country.name if obj.citizenship_country else None

    def get_residence_country_name(self, obj):
        """Get the name of the residence country."""
        return obj.residence_country.name if obj.residence_country else None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["email"] = instance.user.email if instance.user else None
        return ret

    def update(self, instance, validated_data):
        email = validated_data.pop("email", None)
        instance = super().update(instance, validated_data)
        if email is not None and instance.user:
            instance.user.email = email
            instance.user.save(update_fields=["email"])
        return instance

    def get_fields(self):
        fields = super().get_fields()
        fields["citizenship_country"].queryset = Country.objects.all()
        fields["residence_country"].queryset = Country.objects.all()
        return fields
