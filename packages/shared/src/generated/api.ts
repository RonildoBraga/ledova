export interface ApiPaths {
  '/api/assets/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_assets_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/assets/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_assets_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/assets/{uuid}/snapshots/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_assets_snapshots_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/assets/exchange-rates/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_assets_exchange_rates_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/auth/verify/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_auth_verify_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/change-password/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_change_password_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/device-tokens/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_device_tokens_list'];
    put?: never;
    post: ApiOperations['api_device_tokens_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/device-tokens/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_device_tokens_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/device-tokens/register/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_device_tokens_register_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/device-tokens/unregister/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_device_tokens_unregister_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/email-verification/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_email_verification_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/favourite-assets/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_favourite_assets_list'];
    put?: never;
    post: ApiOperations['api_favourite_assets_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/favourite-assets/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_favourite_assets_retrieve'];
    put?: never;
    post?: never;
    delete: ApiOperations['api_favourite_assets_destroy'];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/feature-flags/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_feature_flags_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/feature-flags/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_feature_flags_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/fiat-purchases/transak-widget-url/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_fiat_purchases_transak_widget_url_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/financial-profiles/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_financial_profiles_list'];
    put?: never;
    post: ApiOperations['api_financial_profiles_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/financial-profiles/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_financial_profiles_retrieve'];
    put: ApiOperations['api_financial_profiles_update'];
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch: ApiOperations['api_financial_profiles_partial_update'];
    trace?: never;
  };
  '/api/investor-classifications/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_investor_classifications_list'];
    put?: never;
    post: ApiOperations['api_investor_classifications_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/investor-classifications/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_investor_classifications_retrieve'];
    put?: never;
    post?: never;
    delete: ApiOperations['api_investor_classifications_destroy'];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/investor-classifications/{uuid}/evidence/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_investor_classifications_evidence_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/investor-classifications/eligibility/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_investor_classifications_eligibility_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/notification-preferences/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_notification_preferences_list'];
    put?: never;
    post: ApiOperations['api_notification_preferences_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/notification-preferences/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_notification_preferences_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch: ApiOperations['api_notification_preferences_partial_update'];
    trace?: never;
  };
  '/api/notifications/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_notifications_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/notifications/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_notifications_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch: ApiOperations['api_notifications_partial_update'];
    trace?: never;
  };
  '/api/notifications/mark-all-read/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_notifications_mark_all_read_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/notifications/unread-count/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_notifications_unread_count_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/operator/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_operator_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/portfolios/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_portfolios_list'];
    put?: never;
    post: ApiOperations['api_portfolios_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/portfolios/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_portfolios_retrieve'];
    put: ApiOperations['api_portfolios_update'];
    post?: never;
    delete: ApiOperations['api_portfolios_destroy'];
    options?: never;
    head?: never;
    patch: ApiOperations['api_portfolios_partial_update'];
    trace?: never;
  };
  '/api/portfolios/{uuid}/add-wallet/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_portfolios_add_wallet_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/portfolios/{uuid}/remove-wallet/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_portfolios_remove_wallet_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/portfolios/{uuid}/snapshots/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_portfolios_snapshots_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/resend-verification/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_resend_verification_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/signin/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_signin_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/signout-all/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_signout_all_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/signout/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_signout_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/signup/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_signup_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/token/refresh/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_token_refresh_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/transactions/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_transactions_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/transactions/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_transactions_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/user-accounts/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_user_accounts_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/user-accounts/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_user_accounts_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch: ApiOperations['api_user_accounts_partial_update'];
    trace?: never;
  };
  '/api/user-preferences/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_user_preferences_list'];
    put?: never;
    post: ApiOperations['api_user_preferences_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/user-preferences/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_user_preferences_retrieve'];
    put: ApiOperations['api_user_preferences_update'];
    post?: never;
    delete: ApiOperations['api_user_preferences_destroy'];
    options?: never;
    head?: never;
    patch: ApiOperations['api_user_preferences_partial_update'];
    trace?: never;
  };
  '/api/user-profiles/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_user_profiles_list'];
    put?: never;
    post: ApiOperations['api_user_profiles_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/user-profiles/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_user_profiles_retrieve'];
    put: ApiOperations['api_user_profiles_update'];
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch: ApiOperations['api_user_profiles_partial_update'];
    trace?: never;
  };
  '/api/user-profiles/delete-account/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_user_profiles_delete_account_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/user-profiles/export-data/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_user_profiles_export_data_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/users/identity-verification/status/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_users_identity_verification_status_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/users/identity-verification/token/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_users_identity_verification_token_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_companies_list'];
    put?: never;
    post: ApiOperations['api_v1_companies_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{company_uuid}/documents/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_companies_documents_list'];
    put?: never;
    post: ApiOperations['api_v1_companies_documents_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{company_uuid}/documents/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_companies_documents_retrieve'];
    put?: never;
    post?: never;
    delete: ApiOperations['api_v1_companies_documents_destroy'];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{company_uuid}/documents/{uuid}/file/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_companies_documents_file_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_companies_retrieve'];
    put: ApiOperations['api_v1_companies_update'];
    post?: never;
    delete: ApiOperations['api_v1_companies_destroy'];
    options?: never;
    head?: never;
    patch: ApiOperations['api_v1_companies_partial_update'];
    trace?: never;
  };
  '/api/v1/companies/{uuid}/api-key/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_companies_api_key_retrieve'];
    put?: never;
    post: ApiOperations['api_v1_companies_api_key_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{uuid}/application-status/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_companies_application_status_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{uuid}/resubmit/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_companies_resubmit_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{uuid}/stats/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_companies_stats_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{uuid}/status/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_companies_status_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{uuid}/submit/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_companies_submit_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/companies/{uuid}/withdraw/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_companies_withdraw_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/directory/tokens/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_directory_tokens_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/directory/tokens/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_directory_tokens_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/documents/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_documents_list'];
    put?: never;
    post: ApiOperations['api_v1_documents_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/documents/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_documents_retrieve'];
    put?: never;
    post?: never;
    delete: ApiOperations['api_v1_documents_destroy'];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/documents/{uuid}/attach/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_documents_attach_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/documents/{uuid}/file/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_documents_file_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/offerings/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_offerings_list'];
    put?: never;
    post: ApiOperations['api_v1_offerings_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/offerings/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_offerings_retrieve'];
    put: ApiOperations['api_v1_offerings_update'];
    post?: never;
    delete: ApiOperations['api_v1_offerings_destroy'];
    options?: never;
    head?: never;
    patch: ApiOperations['api_v1_offerings_partial_update'];
    trace?: never;
  };
  '/api/v1/offerings/{uuid}/submit/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_offerings_submit_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/offerings/{uuid}/subscriptions/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_offerings_subscriptions_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/offerings/{uuid}/withdraw/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_offerings_withdraw_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/subscriptions/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_subscriptions_list'];
    put?: never;
    post: ApiOperations['api_v1_subscriptions_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/subscriptions/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_subscriptions_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/subscriptions/{uuid}/submit/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_subscriptions_submit_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/subscriptions/{uuid}/withdraw/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_subscriptions_withdraw_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_list'];
    put?: never;
    post: ApiOperations['api_v1_tokens_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_retrieve'];
    put: ApiOperations['api_v1_tokens_update'];
    post?: never;
    delete: ApiOperations['api_v1_tokens_destroy'];
    options?: never;
    head?: never;
    patch: ApiOperations['api_v1_tokens_partial_update'];
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/deploy/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_tokens_deploy_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/holders/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_holders_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/issuances/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_issuances_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/issue/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_tokens_issue_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/pause-submissions/{submission_id}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_pause_submissions_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/pause/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_tokens_pause_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/register/export/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_register_export_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/{uuid}/unpause/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_tokens_unpause_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/capital-increases/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_capital_increases_list'];
    put?: never;
    post: ApiOperations['api_v1_tokens_capital_increases_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/capital-increases/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_capital_increases_retrieve'];
    put: ApiOperations['api_v1_tokens_capital_increases_update'];
    post?: never;
    delete: ApiOperations['api_v1_tokens_capital_increases_destroy'];
    options?: never;
    head?: never;
    patch: ApiOperations['api_v1_tokens_capital_increases_partial_update'];
    trace?: never;
  };
  '/api/v1/tokens/capital-increases/{uuid}/submit/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_tokens_capital_increases_submit_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/issuance-requests/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_issuance_requests_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/tokens/issuance-requests/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_tokens_issuance_requests_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/events/stream/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['trading_events_stream_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/action-context/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_action_context_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/cancel/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_orders_cancel_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/cancel/message/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_cancel_message_retrieve'];
    put?: never;
    post: ApiOperations['api_v1_trading_orders_cancel_message_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/modifications/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_modifications_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/modify/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_orders_modify_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/modify/message/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_orders_modify_message_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/swap/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_swap_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/swap/approval-broadcast/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_orders_swap_approval_broadcast_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/swap/approval-data/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_swap_approval_data_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/swap/approval-status/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_swap_approval_status_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/{uuid}/swap/sign/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_orders_swap_sign_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/actions/{action_id}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_actions_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/create/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_orders_create_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/create/message/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_orders_create_message_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/orders/submissions/{submission_id}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_orders_submissions_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/swaps/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_swaps_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/tokens/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_tokens_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/tokens/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_tokens_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/tokens/{uuid}/market-data/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_tokens_market_data_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/tokens/{uuid}/order-book/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_tokens_order_book_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/transfers/broadcast/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_transfers_broadcast_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/transfers/prepare/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_trading_transfers_prepare_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/wallets/balances/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_wallets_balances_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/trading/whitelist/{address}/status/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_trading_whitelist_status_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/whitelist/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_whitelist_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/whitelist/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_whitelist_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/whitelist/add/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_whitelist_add_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/whitelist/batch-add/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_whitelist_batch_add_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/whitelist/entry/{address}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_whitelist_entry_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/whitelist/export/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_v1_whitelist_export_retrieve'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/whitelist/remove/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_whitelist_remove_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/whitelist/sync/{address}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_v1_whitelist_sync_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/wallets/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_wallets_list'];
    put?: never;
    post: ApiOperations['api_wallets_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/wallets/{uuid}/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_wallets_retrieve'];
    put: ApiOperations['api_wallets_update'];
    post?: never;
    delete: ApiOperations['api_wallets_destroy'];
    options?: never;
    head?: never;
    patch: ApiOperations['api_wallets_partial_update'];
    trace?: never;
  };
  '/api/wallets/{uuid}/broadcast-transfer/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_wallets_broadcast_transfer_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/wallets/{uuid}/holdings/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: ApiOperations['api_wallets_holdings_list'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/wallets/{uuid}/prepare-transfer/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_wallets_prepare_transfer_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/wallets/{uuid}/request-verification/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_wallets_request_verification_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/wallets/{uuid}/sync/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_wallets_sync_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/wallets/{uuid}/verify-signature/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_wallets_verify_signature_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/wallets/batch-check-balances/': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: ApiOperations['api_wallets_batch_check_balances_create'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type ApiWebhooks = Record<string, never>;
export interface ApiComponents {
  schemas: {
    _CompanyUserProfile: {
      fullName: string | null;
    };
    _CompanyUserProfileCreateRequest: {
      firstName: string;
      lastName: string;
      phone?: string;
    };
    AccountExportData: {
      account: ApiComponents['schemas']['ExportedAccount'] | null;
      exportedAt: string;
      financialProfile: ApiComponents['schemas']['ExportedFinancialProfile'] | null;
      portfolios: ApiComponents['schemas']['ExportedPortfolio'][];
      preferences: ApiComponents['schemas']['ExportedPreferences'] | null;
      profile: ApiComponents['schemas']['ExportedProfile'] | null;
      transactions: ApiComponents['schemas']['ExportedTransaction'][];
      user: ApiComponents['schemas']['ExportedUser'];
      wallets: ApiComponents['schemas']['ExportedWallet'][];
    };
    AccountSummary: {
      accountNumber: string;
      accountType: ApiComponents['schemas']['AccountTypeEnum'];
      activationDate: string | null;
      role: ApiComponents['schemas']['RoleEnum'];
      uuid: string;
    };
    AccountTypeEnum: 'individual';
    ActionEnum: 'add' | 'remove';
    ApplicationResubmitRequest: {
      response: string;
    };
    ApplicationStatus: {
      activatedAt: string | null;
      approvedAt: string | null;
      infoRequestedAt: string | null;
      infoRequestReason: string;
      isActive: boolean;
      isApproved: boolean;
      isPendingReview: boolean;
      name: string;
      rejectionAt: string | null;
      rejectionReason: string;
      reviewCompletedAt: string | null;
      reviewStartedAt: string | null;
      status: ApiComponents['schemas']['CompanyStatusEnum'];
      statusDisplay: string;
      submittedAt: string | null;
      uuid: string;
      withdrawalReason: string;
      withdrawnAt: string | null;
    };
    ApplicationWithdrawRequest: {
      reason?: string;
    };
    ApprovalDataResponse:
      | ApiComponents['schemas']['SettlementSufficientApproval']
      | ApiComponents['schemas']['SettlementApprovalTransaction'];
    ApprovalRequiredEnum: true;
    ApprovalSufficientEnum: false;
    ApprovalTransaction: {
      chainId: string;
      data: string;
      from: string;
      gas: string;
      gasPrice: string;
      nonce: string;
      to: string;
      value: string;
    };
    Asset: {
      assetType: ApiComponents['schemas']['AssetTypeEnum'];
      assetTypeDisplay: string;
      chain: string | null;
      chainDeployments: ApiComponents['schemas']['AssetChainDeployment'][];
      contractAddress: string | null;
      createdAt: string;
      currentPrice: string | null;
      decimals?: number;
      isActive?: boolean;
      isYieldToken: boolean;
      lastNavUpdate: string | null;
      name: string;
      navPerToken: string | null;
      priceCurrency?: string;
      symbol: string;
      updatedAt: string;
      uuid: string;
      valueSource: ApiComponents['schemas']['ValueSourceEnum'];
    };
    AssetChainDeployment: {
      chain: string;
      contractAddress?: string | null;
      decimals?: number;
      isActive?: boolean;
      uuid: string;
    };
    AssetSnapshot: {
      asset: string;
      assetSymbol: string;
      blockNumber?: number | null;
      createdAt: string;
      dataSource: string;
      marketData?: unknown;
      price: string;
      priceCurrency?: string;
      sourceTimestamp: string;
      txHash?: string | null;
      updatedAt: string;
      uuid: string;
    };
    AssetTypeEnum:
      'native_crypto' | 'erc20_token' | 'stablecoin' | 'tokenized_security' | 'tokenized_rwa' | 'synthetic';
    AuthCookieRefreshed: {
      message: string;
    };
    AuthEmailVerified: {
      email: string;
      isEmailVerified: boolean;
      tokens?: ApiComponents['schemas']['AuthTokenPair'][];
      uuid: string | null;
    };
    AuthIdentity: {
      email: string;
      isEmailVerified: boolean;
      uuid: string | null;
    };
    AuthPasswordChanged: {
      message: string;
    };
    AuthRefreshError: {
      error: string;
    };
    AuthRefreshRequestRequest: {
      refresh?: ((string | null) | 0 | false | unknown[] | Record<string, never>) | null;
    };
    AuthRefreshResponse:
      ApiComponents['schemas']['AuthTokensRefreshed'] | ApiComponents['schemas']['AuthCookieRefreshed'];
    AuthSession: {
      email: string;
      isEmailVerified: boolean;
      tokens?: ApiComponents['schemas']['AuthTokenPair'][];
      uuid: string | null;
    };
    AuthSessionValidity: {
      expiresAt?: string;
      valid: boolean;
    };
    AuthSignedOut: {
      message: string;
    };
    AuthSignedOutEverywhere: {
      message: string;
    };
    AuthSignoutRequestRequest: {
      refresh?: ((string | null) | 0 | false | unknown[] | Record<string, never>) | null;
    };
    AuthTokenPair: {
      accessToken: string;
      refreshToken: string;
    };
    AuthTokensRefreshed: {
      access: string;
      refresh: string;
    };
    AuthVerificationResent: {
      message: string;
    };
    BatchBalanceRequestRequest: {
      addresses: string[];
      chain: ApiComponents['schemas']['SupportedWalletChainEnum'];
    };
    BatchBalanceResponse: {
      balances: {
        [key: string]: string | null;
      };
      chain: ApiComponents['schemas']['SupportedWalletChainEnum'];
      errors?: string[];
      userAccount: string;
    };
    BlankEnum: '';
    BroadcastTransferRequest: {
      amount?: string | null;
      signedTransaction: string;
      toAddress?: string | null;
      tokenContract?: string | null;
      transactionFee?: string | null;
    };
    BroadcastTransferResponse: {
      message: string;
      pendingTransaction: ApiComponents['schemas']['PendingTransfer'] | null;
      status: ApiComponents['schemas']['BroadcastTransferResponseStatusEnum'];
      success: boolean;
      txHash: string;
    };
    BroadcastTransferResponseStatusEnum: 'pending' | 'confirmed' | 'failed' | 'reorged' | 'replaced';
    CapitalIncreaseCreateRequestRequest: {
      additionalShares: number;
      boardResolutionReference: string;
      newAuthorizedTotal: number;
      purpose: string;
      shareholderApprovalReference?: string;
      token: string;
    };
    CapitalIncreaseDetail: {
      additionalShares: number;
      boardResolutionReference: string;
      canBeEdited: boolean;
      canBeSubmitted: boolean;
      createdAt: string;
      dilutionPercentage: string | null;
      executedAt: string | null;
      executedIssuance: string | null;
      executionNotes: string;
      newAuthorizedTotal: number;
      purpose: string;
      rejectionReason: string;
      reviewedAt: string | null;
      reviewedBy: number | null;
      reviewedByEmail: string | null;
      shareholderApprovalReference: string;
      status: ApiComponents['schemas']['CapitalRequestStatusEnum'];
      statusDisplay: string;
      submittedAt: string | null;
      submittedBy: number | null;
      submittedByEmail: string | null;
      token: string;
      tokenName: string;
      tokenSymbol: string;
      updatedAt: string;
      uuid: string;
    };
    CapitalIncreaseList: {
      additionalShares: number;
      createdAt: string;
      dilutionPercentage: string | null;
      newAuthorizedTotal: number;
      purpose: string;
      status: ApiComponents['schemas']['CapitalRequestStatusEnum'];
      statusDisplay: string;
      submittedAt: string | null;
      submittedBy: number | null;
      submittedByEmail: string | null;
      token: string;
      tokenName: string;
      tokenSymbol: string;
      uuid: string;
    };
    CapitalIncreaseSubmitted: {
      message: string;
      request: ApiComponents['schemas']['CapitalIncreaseDetail'];
    };
    CapitalIncreaseUpdate: {
      additionalShares: number;
      boardResolutionReference: string;
      newAuthorizedTotal: number;
      purpose: string;
      shareholderApprovalReference?: string;
    };
    CapitalIncreaseUpdateRequest: {
      additionalShares: number;
      boardResolutionReference: string;
      newAuthorizedTotal: number;
      purpose: string;
      shareholderApprovalReference?: string;
    };
    CapitalRequestStatusEnum:
      | 'draft'
      | 'submitted'
      | 'under_review'
      | 'approved'
      | 'rejected'
      | 'executing'
      | 'executed'
      | 'failed'
      | 'superseded';
    CategoryEnum: 'product_value' | 'accountant_certificate' | 'professional_investor' | 'associated_person';
    CertifierBodyEnum: 'ca_anz' | 'cpa_australia' | 'ipa';
    ChangePasswordRequest: {
      currentPassword: string;
      newPassword: string;
      newPasswordConfirm: string;
    };
    CompanyAPIKey: {
      apiKey: string;
      apiKeyCreatedAt: string;
    };
    CompanyApplicationResubmitted: {
      company: ApiComponents['schemas']['ApplicationStatus'];
      message: string;
    };
    CompanyApplicationSubmitted: {
      company: ApiComponents['schemas']['ApplicationStatus'];
      message: string;
    };
    CompanyApplicationWithdrawn: {
      company: ApiComponents['schemas']['ApplicationStatus'];
      message: string;
    };
    CompanyDetail: {
      abn?: string;
      acn: string;
      activatedAt: string | null;
      additionalInfoResponse: string;
      addressLine1?: string;
      addressLine2?: string;
      approvedAt: string | null;
      canIssueTokens: boolean;
      city?: string;
      companyType?: ApiComponents['schemas']['CompanyTypeEnum'];
      companyTypeDisplay: string;
      country?: string;
      createdAt: string;
      description?: string;
      displayName: string;
      documents: ApiComponents['schemas']['CompanyDocument'][];
      email: string;
      foundedYear?: number | null;
      industry?: string;
      infoRequestedAt: string | null;
      infoRequestReason: string;
      isActive: boolean;
      isApproved: boolean;
      isOpenToInvestors?: boolean;
      isPendingReview: boolean;
      name: string;
      operatorWallet: string;
      phone?: string;
      postcode?: string;
      primaryContact: ApiComponents['schemas']['_CompanyUserProfile'] | null;
      rejectionAt: string | null;
      rejectionReason: string;
      reviewStartedAt: string | null;
      state?: string;
      status: ApiComponents['schemas']['CompanyStatusEnum'];
      statusDisplay: string;
      submittedAt: string | null;
      tradingName?: string;
      updatedAt: string;
      uuid: string;
      withdrawalReason: string;
      withdrawnAt: string | null;
    };
    CompanyDocument: {
      createdAt: string;
      documentType: ApiComponents['schemas']['CompanyDocumentDocumentTypeEnum'];
      documentTypeDisplay: string;
      fileSize?: number;
      fileUrl: string;
      isVerified: boolean;
      mimeType?: string;
      name: string;
      uuid: string;
      verifiedAt: string | null;
    };
    CompanyDocumentDocumentTypeEnum:
      | 'cert_inc'
      | 'asic'
      | 'constitution'
      | 'share_register'
      | 'financials'
      | 'auditor_report'
      | 'director_id'
      | 'beneficial_ownership'
      | 'shareholder'
      | 'business_plan'
      | 'risk_disclosure'
      | 'prospectus'
      | 'legal_opinion'
      | 'tax_return'
      | 'bank_statement'
      | 'other';
    CompanyDocumentRequest: {
      documentType: ApiComponents['schemas']['CompanyDocumentDocumentTypeEnum'];
      externalUrl?: string;
      file?: Blob;
      fileSize?: number;
      mimeType?: string;
      name: string;
    };
    CompanyList: {
      acn: string;
      city: string;
      companyType: ApiComponents['schemas']['CompanyTypeEnum'];
      companyTypeDisplay: string;
      createdAt: string;
      displayName: string;
      industry: string;
      isActive: boolean;
      isApproved: boolean;
      name: string;
      state: string;
      status: ApiComponents['schemas']['CompanyStatusEnum'];
      statusDisplay: string;
      tradingName: string;
      uuid: string;
    };
    CompanyRegistered: {
      company: ApiComponents['schemas']['CompanyDetail'];
      message: string;
    };
    CompanyRegistrationRequest: {
      abn?: string;
      acn: string;
      companyType?: ApiComponents['schemas']['CompanyTypeEnum'];
      name: string;
      primaryContact: ApiComponents['schemas']['_CompanyUserProfileCreateRequest'];
      tradingName?: string;
    };
    CompanyStats: {
      pendingActions: number;
      pendingCapitalIncreases: number;
      totalShareholders: number;
      totalTokens: number;
    };
    CompanyStatusEnum:
      | 'draft'
      | 'submitted'
      | 'review'
      | 'info_required'
      | 'approved'
      | 'active'
      | 'warning'
      | 'suspended'
      | 'delisted'
      | 'rejected'
      | 'withdrawn';
    CompanyStatusUpdated: {
      company: ApiComponents['schemas']['CompanyDetail'];
      message: string;
    };
    CompanyStatusUpdateRequest: {
      attestOfficeholder?: boolean;
      boardResolutionReference?: string;
      declarantName?: string;
      reason?: string;
      status: ApiComponents['schemas']['CompanyStatusEnum'];
    };
    CompanyTypeEnum: 'pty' | 'public' | 'unlisted';
    CompanyUpdate: {
      abn?: string;
      acn: string;
      addressLine1?: string;
      addressLine2?: string;
      city?: string;
      companyType?: ApiComponents['schemas']['CompanyTypeEnum'];
      description?: string;
      industry?: string;
      isOpenToInvestors?: boolean;
      name: string;
      operatorWallet?: string | null;
      phone?: string;
      postcode?: string;
      state?: string;
      tradingName?: string;
    };
    CompanyUpdateRequest: {
      abn?: string;
      acn: string;
      addressLine1?: string;
      addressLine2?: string;
      city?: string;
      companyType?: ApiComponents['schemas']['CompanyTypeEnum'];
      description?: string;
      industry?: string;
      isOpenToInvestors?: boolean;
      name: string;
      operatorWallet?: string | null;
      phone?: string;
      postcode?: string;
      state?: string;
      tradingName?: string;
    };
    DeletedAccountResponse: {
      message: string;
    };
    DeploymentModeEnum: 'single_issuer' | 'registry';
    DeviceToken: {
      createdAt: string;
      deviceType: ApiComponents['schemas']['DeviceTypeEnum'];
      isActive?: boolean;
      lastUsedAt: string;
      pushToken: string;
      uuid: string;
    };
    DeviceTokenNotFound: {
      detail: string;
    };
    DeviceTokenRequest: {
      deviceType: ApiComponents['schemas']['DeviceTypeEnum'];
      isActive?: boolean;
      pushToken: string;
    };
    DeviceTypeEnum: 'ios' | 'android';
    DirectoryCompany: {
      city: string;
      displayName: string;
      industry: string;
      state: string;
    };
    DirectoryOpenOfferingResponse: {
      closesAt: string | null;
      opensAt: string;
      priceCurrency: string;
      pricePerShare: string;
      uuid: string;
    };
    DirectoryTokenList: {
      bestAsk: string | null;
      bestBid: string | null;
      chain: string | null;
      company: ApiComponents['schemas']['DirectoryCompany'];
      companyName: string;
      companyUuid: string;
      contractAddress: string | null;
      createdAt: string;
      decimals: number;
      deployedAt: string | null;
      isDivisible: boolean;
      issuedShares: number;
      isTransferable: boolean;
      lastPrice: string | null;
      name: string;
      openOffering: ApiComponents['schemas']['DirectoryOpenOfferingResponse'] | null;
      status: ApiComponents['schemas']['ShareTokenStatusEnum'];
      statusDisplay: string;
      symbol: string;
      tokenType: ApiComponents['schemas']['TokenTypeEnum'];
      tokenTypeDisplay: string;
      totalSupply: string;
      uuid: string;
    };
    DisplayCurrencyEnum: 'AUD' | 'USD';
    Document: {
      attachedAt: string | null;
      classification: string | null;
      createdAt: string;
      documentType: ApiComponents['schemas']['UserDocumentTypeEnum'];
      fileUrl: string | null;
      latestExtraction: ApiComponents['schemas']['DocumentExtraction'] | null;
      mimeType: string;
      note: string;
      originalFilename: string;
      purgedAt: string | null;
      retentionUntil: string | null;
      updatedAt: string;
      uuid: string;
    };
    DocumentAttachmentRequest: {
      classification: string;
    };
    DocumentExtraction: {
      confidence: number | null;
      createdAt: string;
      durationMs: number | null;
      error: string;
      finishedAt: string | null;
      modelName: string;
      parsedJson: unknown;
      startedAt: string | null;
      status: ApiComponents['schemas']['DocumentExtractionStatusEnum'];
      updatedAt: string;
      uuid: string;
      warnings: unknown;
    };
    DocumentExtractionStatusEnum: 'pending' | 'running' | 'succeeded' | 'failed';
    DocumentUploadRequest: {
      classification?: string | null;
      documentType?: ApiComponents['schemas']['UserDocumentTypeEnum'];
      file: Blob;
      note?: string;
    };
    EmailVerificationRequest: {
      email: string;
      token: string;
    };
    ExchangeRateResponse: {
      baseCurrency: string;
      rate: string;
      targetCurrency: string;
    };
    ExemptionEnum:
      | 's708_8_minimum_amount'
      | 's708_8_net_assets'
      | 's708_8_gross_income'
      | 's708_11_professional'
      | 's761g_wholesale_client';
    ExportedAccount: {
      accountNumber: string;
      accountType: string;
      activationDate: string | null;
      createdAt: string;
      uuid: string;
    };
    ExportedFinancialProfile: {
      intendedUse: string | null;
      intendedUseOtherText: string | null;
      occupation: string | null;
      sourceOfFunds: unknown;
      sourceOfFundsOtherText: string | null;
    };
    ExportedPortfolio: {
      createdAt: string;
      isActive: boolean;
      name: string;
      uuid: string;
    };
    ExportedPreferences: {
      selectedPortfolio: string | null;
    };
    ExportedProfile: {
      citizenshipCountry: string | null;
      createdAt: string;
      dateOfBirth: string | null;
      fullName: string | null;
      isIdVerified: boolean;
      phoneCountryCode: string | null;
      phoneNumber: string | null;
      residentialAddress: string | null;
    };
    ExportedTransaction: {
      amount: string;
      asset: string | null;
      blockTimestamp: string | null;
      chain: string;
      createdAt: string;
      fromAddress: string;
      status: string;
      toAddress: string | null;
      transactionFee: string | null;
      txHash: string;
      uuid: string;
    };
    ExportedUser: {
      dateJoined: string;
      email: string;
      isEmailVerified: boolean;
    };
    ExportedWallet: {
      address: string;
      chain: string;
      createdAt: string;
      isVerified: boolean;
      marketValue: string;
      name: string | null;
      nativeBalance: string;
      uuid: string;
    };
    ExtractedApplicantData: {
      address: string | null;
      dateOfBirth: string | null;
      fullName: string | null;
      residenceCountry?: string | null;
    };
    FavouriteAsset: {
      asset: ApiComponents['schemas']['Asset'];
      createdAt: string;
      updatedAt: string;
      userAccount: string;
      uuid: string;
    };
    FavouriteAssetRequest: {
      asset: string;
    };
    FeatureFlag: {
      description?: string;
      enabled?: boolean;
      minAppVersion?: string;
      name: string;
      platform?: ApiComponents['schemas']['PlatformEnum'];
      uuid: string;
    };
    FiatPurchaseWidget: {
      chain: string;
      cryptoCurrency: string;
      url: string;
      walletAddress: string;
    };
    FiatPurchaseWidgetRequestRequest: {
      cryptoCurrencyCode?: ((string | null) | 0 | false | unknown[] | Record<string, never>) | null;
      defaultFiatAmount?: ((number | null) | string | boolean | unknown[] | Record<string, never>) | null;
      defaultFiatCurrency?: ((string | null) | 0 | false | unknown[] | Record<string, never>) | null;
      fiatAmount?: ((number | null) | string | boolean | unknown[] | Record<string, never>) | null;
      fiatCurrency?: ((string | null) | 0 | false | unknown[] | Record<string, never>) | null;
      redirectUrl?: unknown;
      themeColor?: unknown;
      walletUuid: string;
    };
    FieldEnum: 'quantity' | 'min_quantity' | 'price_per_share';
    FinancialProfile: {
      intendedUse?:
        | (
            | ApiComponents['schemas']['IntendedUseEnum']
            | ApiComponents['schemas']['BlankEnum']
            | ApiComponents['schemas']['NullEnum']
          )
        | null;
      intendedUseOtherText?: string | null;
      occupation?: string | null;
      sourceOfFunds?: unknown;
      sourceOfFundsOtherText?: string | null;
      userProfile: string;
      uuid: string;
    };
    FinancialProfileRequest: {
      intendedUse?:
        | (
            | ApiComponents['schemas']['IntendedUseEnum']
            | ApiComponents['schemas']['BlankEnum']
            | ApiComponents['schemas']['NullEnum']
          )
        | null;
      intendedUseOtherText?: string | null;
      occupation?: string | null;
      sourceOfFunds?: unknown;
      sourceOfFundsOtherText?: string | null;
    };
    FormerMember: {
      ceasedAtBlock: number;
      ceasedOn: string;
      identityRecordedAt: string;
      identitySource: ApiComponents['schemas']['IdentitySourceEnum'];
      identitySourceDisplay: string;
      name: string;
      residentialAddress: string;
      sharesAtCessation: string;
      uuid: string;
      walletAddress: string;
    };
    HolderTypeEnum: 'member' | 'treasury' | 'ambiguous' | 'unidentified';
    Holding: {
      asset: ApiComponents['schemas']['Asset'];
      assetName: string;
      assetSymbol: string;
      assetUuid: string;
      chain: string;
      createdAt: string;
      lastSyncedAt: string | null;
      marketValue: string | null;
      quantity: string;
      updatedAt: string;
      uuid: string;
      valueSource: ApiComponents['schemas']['ValueSourceEnum'];
      walletAddress: string;
      walletUuid: string;
    };
    HttpStatusEnum: 400 | 409;
    IdentitySourceEnum: 'profile' | 'stamped' | 'recorded' | 'treasury_label' | 'unresolvable' | 'none' | 'unknown';
    IdentityVerificationSession: {
      accessToken: string | null;
      applicantId: string | null;
      formUrl: string | null;
      provider: string;
    };
    IdentityVerificationStatus: {
      applicantId: string | null;
      extractedData: ApiComponents['schemas']['ExtractedApplicantData'] | null;
      isVerified: boolean;
      needsRetry: boolean;
      provider: string;
      rejectionLabels: string[];
      reviewAnswer: string | null;
      reviewResult: string | null;
      status: string | null;
      verifiedAt: string | null;
    };
    IntendedUseEnum: 'long_term_investment' | 'trading_crypto' | 'savings' | 'other';
    InvestorClassification: {
      category: ApiComponents['schemas']['CategoryEnum'];
      categoryDisplay: string;
      certificateIssuedAt?: string | null;
      certifierBody?: ApiComponents['schemas']['CertifierBodyEnum'] | ApiComponents['schemas']['BlankEnum'];
      certifierMembershipNumber?: string;
      certifierName?: string;
      company?: string | null;
      createdAt: string;
      declarationAccepted?: boolean;
      declarationText: string;
      declaredBasis?: string;
      evidenceFileSize: number | null;
      evidenceMimeType: string;
      evidenceUrl: string | null;
      expiresAt: string | null;
      isExpired: boolean;
      isLive: boolean;
      rejectionReason: string;
      reviewedAt: string | null;
      reviewNotes: string;
      status: ApiComponents['schemas']['InvestorClassificationStatusEnum'];
      statusDisplay: string;
      submittedAt: string | null;
      userAccount: string;
      uuid: string;
    };
    InvestorClassificationRequest: {
      category: ApiComponents['schemas']['CategoryEnum'];
      certificateIssuedAt?: string | null;
      certifierBody?: ApiComponents['schemas']['CertifierBodyEnum'] | ApiComponents['schemas']['BlankEnum'];
      certifierMembershipNumber?: string;
      certifierName?: string;
      company?: string | null;
      declarationAccepted?: boolean;
      declaredBasis?: string;
      evidenceFile: Blob;
    };
    InvestorClassificationStatusEnum: 'submitted' | 'verified' | 'rejected' | 'revoked' | 'withdrawn';
    InvestorEligibility: {
      account: string | null;
      classification: ApiComponents['schemas']['InvestorClassification'] | null;
      isEligible: boolean;
      reasons: string[];
    };
    IssuanceTypeEnum: 'initial' | 'additional' | 'bonus' | 'dividend' | 'transfer';
    IssuerSubscription: {
      allotmentState: string;
      allottedQuantity: number | null;
      amountDue: string;
      amountReceived: string | null;
      createdAt: string;
      investorName: string;
      paymentConfirmedAt: string | null;
      paymentDueAt: string | null;
      pricePerShare: string;
      quantity: number;
      reference: string;
      settlementRailDisplay: string;
      status: ApiComponents['schemas']['SubscriptionStatusEnum'];
      statusDisplay: string;
      uuid: string;
      walletAddress: string;
    };
    KycProviderEnum: 'sumsub' | 'kycaid';
    MarkAllReadResponse: {
      marked: number;
    };
    MarketData: {
      bestAsk: string | null;
      bestBid: string | null;
      lastTrade: ApiComponents['schemas']['MarketLastTrade'] | null;
      lastTradePrice: string | null;
      midpointPrice: string | null;
      symbol: string;
      token: string;
    };
    MarketLastTrade: {
      completedAt: string | null;
      paymentAmount: string;
      paymentToken: string;
      price: string;
      shares: number;
    };
    NameEnum: 'LedovaAtomicSwap';
    NetworkEnum: 'BTC';
    Notification: {
      body: string;
      createdAt: string;
      data: unknown;
      isArchived?: boolean;
      isRead?: boolean;
      notificationType: ApiComponents['schemas']['NotificationTypeEnum'];
      readAt: string | null;
      title: string;
      updatedAt: string;
      uuid: string;
    };
    NotificationPreferences: {
      createdAt: string;
      marketing?: boolean;
      priceAlerts?: boolean;
      transactionAlerts?: boolean;
      updatedAt: string;
      userProfile: string;
      uuid: string;
    };
    NotificationPreferencesRequest: {
      marketing?: boolean;
      priceAlerts?: boolean;
      transactionAlerts?: boolean;
    };
    NotificationRequest: {
      isArchived?: boolean;
      isRead?: boolean;
    };
    NotificationTypeEnum: 'transaction' | 'price' | 'marketing' | 'general' | 'system';
    NullEnum: null;
    OfferingDetail: {
      acceptsBankTransfer: boolean;
      canBeDeleted: boolean;
      canBeEdited: boolean;
      capShares: number;
      closedAt: string | null;
      closeReason: string;
      closesAt: string | null;
      createdAt: string;
      documents: string[];
      exemption: ApiComponents['schemas']['ExemptionEnum'];
      exemptionDisplay: string;
      isOpen: boolean;
      maximumShares: number | null;
      minimumShares: number;
      opensAt: string;
      priceCurrency: ApiComponents['schemas']['PriceCurrencyEnum'];
      pricePerShare: string;
      rejectionReason: string;
      reviewedAt: string | null;
      reviewedByEmail: string | null;
      reviewNotes: string;
      settlementAssets: string[];
      status: ApiComponents['schemas']['OfferingStatusEnum'];
      statusDisplay: string;
      submittedAt: string | null;
      submittedByEmail: string | null;
      summary: string;
      targetShares: number;
      tokenName: string;
      tokenSymbol: string;
      tokenUuid: string;
      updatedAt: string;
      useOfProceeds: string;
      uuid: string;
    };
    OfferingList: {
      canBeDeleted: boolean;
      canBeEdited: boolean;
      capShares: number;
      closeReason: string;
      closesAt: string | null;
      createdAt: string;
      exemption: ApiComponents['schemas']['ExemptionEnum'];
      exemptionDisplay: string;
      isOpen: boolean;
      maximumShares: number | null;
      minimumShares: number;
      opensAt: string;
      priceCurrency: ApiComponents['schemas']['PriceCurrencyEnum'];
      pricePerShare: string;
      rejectionReason: string;
      status: ApiComponents['schemas']['OfferingStatusEnum'];
      statusDisplay: string;
      targetShares: number;
      tokenName: string;
      tokenSymbol: string;
      tokenUuid: string;
      uuid: string;
    };
    OfferingStatusEnum: 'draft' | 'submitted' | 'under_review' | 'approved' | 'rejected' | 'closed' | 'withdrawn';
    OfferingWithdrawRequest: {
      reason?: string;
    };
    OfferingWriteRequest: {
      acceptsBankTransfer?: boolean;
      capShares: number;
      closesAt?: string | null;
      documents?: string[];
      exemption: ApiComponents['schemas']['ExemptionEnum'];
      maximumShares?: number | null;
      minimumShares: number;
      opensAt: string;
      priceCurrency?: ApiComponents['schemas']['PriceCurrencyEnum'];
      pricePerShare: string;
      settlementAssets?: string[];
      summary?: string;
      targetShares: number;
      token: string;
      useOfProceeds?: string;
    };
    Operator: {
      abn: string;
      contactEmail: string;
      deploymentMode: ApiComponents['schemas']['DeploymentModeEnum'];
      investorKycRequired: boolean;
      issuedStablecoin: ApiComponents['schemas']['SettlementAsset'] | null;
      issuerKycRequired: boolean;
      legalName: string;
      name: string;
      paymentInstructions: ApiComponents['schemas']['OperatorPaymentInstructions'] | null;
      supportedSettlementAssets: ApiComponents['schemas']['SettlementAsset'][];
      website: string;
    };
    OperatorPaymentInstructions: {
      bankAccountName?: string;
      bankAccountNumber?: string;
      bankBsb?: string;
      paymentReferencePrefix?: string;
      receivingWalletAddress?: string;
      receivingWalletChain?: string;
    };
    OrderActionAppliedResult:
      ApiComponents['schemas']['OrderActionCancelResult'] | ApiComponents['schemas']['OrderActionModifyResult'];
    OrderActionCancelResult: {
      fromStatus: ApiComponents['schemas']['TransferOrderStatusEnum'];
      kind: ApiComponents['schemas']['OrderActionCancelResultKindEnum'];
      toStatus: ApiComponents['schemas']['ToStatusEnum'];
    };
    OrderActionCancelResultKindEnum: 'cancel';
    OrderActionChallenge: {
      digest: string;
      domain: ApiComponents['schemas']['SigningDomain'];
      expiresAt: string;
      message: ApiComponents['schemas']['SigningMessage'];
      purpose: ApiComponents['schemas']['OrderActionChallengePurposeEnum'];
      types: ApiComponents['schemas']['SigningTypes'];
    };
    OrderActionChallengePurposeEnum: 'order_cancel' | 'order_modify';
    OrderActionChange: {
      field: ApiComponents['schemas']['FieldEnum'];
      new: string;
      old: string;
    };
    OrderActionContext: {
      currentValues: ApiComponents['schemas']['OrderActionCurrentValues'];
      domain: ApiComponents['schemas']['SigningDomain'];
      orderUuid: string;
      ownerAccountUuid: string;
      protocolVersion: number;
      token: ApiComponents['schemas']['OrderActionToken'];
      tokenUuid: string;
      walletAddress: string;
      walletUuid: string;
    };
    OrderActionCurrentValues: {
      canCancel: boolean;
      canModify: boolean;
      filledQuantity: string;
      minQuantity: string;
      modificationCount: number;
      orderType: ApiComponents['schemas']['TransferOrderTypeEnum'];
      pricePerShare: string;
      quantity: string;
      remainingQuantity: string;
      status: ApiComponents['schemas']['TransferOrderStatusEnum'];
    };
    OrderActionExecuteRequestRequest: {
      actionId: string;
      digest?: string;
      ownerAccountUuid: string;
      signature?: string;
    };
    OrderActionIdentityRequest: {
      actionId: string;
      ownerAccountUuid: string;
    };
    OrderActionIntent: {
      domain: ApiComponents['schemas']['SigningDomain'];
      modifications: ApiComponents['schemas']['OrderActionValues'] | null;
    };
    OrderActionModifyRequestRequest: {
      actionId: string;
      newMinQuantity: string;
      newPricePerShare: string;
      newQuantity: string;
      ownerAccountUuid: string;
    };
    OrderActionModifyResult: {
      changes: ApiComponents['schemas']['OrderActionChange'][];
      kind: ApiComponents['schemas']['OrderActionModifyResultKindEnum'];
      modificationCount: number;
    };
    OrderActionModifyResultKindEnum: 'modify';
    OrderActionRefusal: {
      code: ApiComponents['schemas']['OrderActionRefusalCodeEnum'];
      detail: string;
      httpStatus: ApiComponents['schemas']['HttpStatusEnum'];
    };
    OrderActionRefusalCodeEnum:
      'order_cancellation_failed' | 'order_modification_failed' | 'order_modification_conflict';
    OrderActionReview: {
      currentValues: ApiComponents['schemas']['OrderActionCurrentValues'];
      token: ApiComponents['schemas']['OrderActionToken'];
    };
    OrderActionSubmission: {
      actionId: string;
      challenge: ApiComponents['schemas']['OrderActionChallenge'] | null;
      intent: ApiComponents['schemas']['OrderActionIntent'];
      order: ApiComponents['schemas']['SubmissionOrder'];
      orderUuid: string;
      ownerAccountUuid: string;
      protocolVersion: number;
      purpose: ApiComponents['schemas']['OrderActionSubmissionPurposeEnum'];
      refusal: ApiComponents['schemas']['OrderActionRefusal'] | null;
      result: ApiComponents['schemas']['OrderActionAppliedResult'] | null;
      review: ApiComponents['schemas']['OrderActionReview'];
      status: ApiComponents['schemas']['OrderActionSubmissionStatusEnum'];
      tokenUuid: string;
      walletAddress: string;
      walletUuid: string;
    };
    OrderActionSubmissionPurposeEnum: 'cancel' | 'modify';
    OrderActionSubmissionStatusEnum: 'pending' | 'applied' | 'refused';
    OrderActionToken: {
      contractAddress: string;
      name: string;
      symbol: string;
    };
    OrderActionValues: {
      minQuantity: string;
      pricePerShare: string;
      quantity: string;
    };
    OrderBook: {
      buyOrders: ApiComponents['schemas']['OrderBookEntry'][];
      sellOrders: ApiComponents['schemas']['OrderBookEntry'][];
      token: string;
    };
    OrderBookEntry: {
      orders: number;
      price: string;
      quantity: number;
    };
    OrderCreateChallenge: {
      digest: string;
      domain: ApiComponents['schemas']['SigningDomain'];
      expiresAt: string;
      message: ApiComponents['schemas']['SigningMessage'];
      purpose: ApiComponents['schemas']['OrderCreateChallengePurposeEnum'];
      tokenUuid: string;
      types: ApiComponents['schemas']['SigningTypes'];
      walletAddress: string;
    };
    OrderCreateChallengePurposeEnum: 'order_create';
    OrderSubmission: {
      challenge: ApiComponents['schemas']['OrderCreateChallenge'] | null;
      intent: ApiComponents['schemas']['OrderSubmissionIntent'];
      match: ApiComponents['schemas']['OrderSubmissionMatch'] | null;
      order: ApiComponents['schemas']['SubmissionOrder'] | null;
      ownerAccountUuid: string;
      refusal: ApiComponents['schemas']['OrderSubmissionRefusal'] | null;
      status: ApiComponents['schemas']['OrderSubmissionStatusEnum'];
      submissionId: string;
      walletUuid: string;
    };
    OrderSubmissionIntent: {
      minQuantity: string;
      orderType: ApiComponents['schemas']['OrderSubmissionIntentOrderTypeEnum'];
      pricePerShare: string;
      quantity: string;
      token: string;
      walletAddress: string;
    };
    OrderSubmissionIntentOrderTypeEnum: 'buy' | 'sell';
    OrderSubmissionMatch: {
      counterOrder: string;
      matched: boolean;
      swapOrder: string;
    };
    OrderSubmissionRefusal: {
      code: string;
      detail: string;
    };
    OrderSubmissionStatusEnum: 'pending' | 'created' | 'refused';
    PaginatedAssetList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['Asset'][];
    };
    PaginatedCapitalIncreaseListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['CapitalIncreaseList'][];
    };
    PaginatedCompanyDocumentList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['CompanyDocument'][];
    };
    PaginatedCompanyListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['CompanyList'][];
    };
    PaginatedDeviceTokenList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['DeviceToken'][];
    };
    PaginatedDirectoryTokenListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['DirectoryTokenList'][];
    };
    PaginatedDocumentList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['Document'][];
    };
    PaginatedFavouriteAssetList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['FavouriteAsset'][];
    };
    PaginatedFeatureFlagList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['FeatureFlag'][];
    };
    PaginatedFinancialProfileList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['FinancialProfile'][];
    };
    PaginatedInvestorClassificationList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['InvestorClassification'][];
    };
    PaginatedIssuerSubscriptionList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['IssuerSubscription'][];
    };
    PaginatedNotificationList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['Notification'][];
    };
    PaginatedOfferingListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['OfferingList'][];
    };
    PaginatedPortfolioList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['Portfolio'][];
    };
    PaginatedShareIssuanceListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['ShareIssuanceList'][];
    };
    PaginatedShareIssuanceRequestList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['ShareIssuanceRequest'][];
    };
    PaginatedShareTokenListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['ShareTokenList'][];
    };
    PaginatedSubscriptionListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['SubscriptionList'][];
    };
    PaginatedSwapOrderListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['SwapOrderList'][];
    };
    PaginatedTransactionList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['Transaction'][];
    };
    PaginatedTransferOrderListList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['TransferOrderList'][];
    };
    PaginatedUserProfileList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['UserProfile'][];
    };
    PaginatedWalletList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['Wallet'][];
    };
    PaginatedWhitelistEntryList: {
      count: number;
      next?: string | null;
      previous?: string | null;
      results: ApiComponents['schemas']['WhitelistEntry'][];
    };
    PatchedCapitalIncreaseUpdateRequest: {
      additionalShares?: number;
      boardResolutionReference?: string;
      newAuthorizedTotal?: number;
      purpose?: string;
      shareholderApprovalReference?: string;
    };
    PatchedCompanyUpdateRequest: {
      abn?: string;
      acn?: string;
      addressLine1?: string;
      addressLine2?: string;
      city?: string;
      companyType?: ApiComponents['schemas']['CompanyTypeEnum'];
      description?: string;
      industry?: string;
      isOpenToInvestors?: boolean;
      name?: string;
      operatorWallet?: string | null;
      phone?: string;
      postcode?: string;
      state?: string;
      tradingName?: string;
    };
    PatchedFinancialProfileRequest: {
      intendedUse?:
        | (
            | ApiComponents['schemas']['IntendedUseEnum']
            | ApiComponents['schemas']['BlankEnum']
            | ApiComponents['schemas']['NullEnum']
          )
        | null;
      intendedUseOtherText?: string | null;
      occupation?: string | null;
      sourceOfFunds?: unknown;
      sourceOfFundsOtherText?: string | null;
    };
    PatchedNotificationPreferencesRequest: {
      marketing?: boolean;
      priceAlerts?: boolean;
      transactionAlerts?: boolean;
    };
    PatchedNotificationRequest: {
      isArchived?: boolean;
      isRead?: boolean;
    };
    PatchedOfferingWriteRequest: {
      acceptsBankTransfer?: boolean;
      capShares?: number;
      closesAt?: string | null;
      documents?: string[];
      exemption?: ApiComponents['schemas']['ExemptionEnum'];
      maximumShares?: number | null;
      minimumShares?: number;
      opensAt?: string;
      priceCurrency?: ApiComponents['schemas']['PriceCurrencyEnum'];
      pricePerShare?: string;
      settlementAssets?: string[];
      summary?: string;
      targetShares?: number;
      token?: string;
      useOfProceeds?: string;
    };
    PatchedPortfolioRequest: {
      isActive?: boolean;
      name?: string;
    };
    PatchedUserAccountRequest: {
      accountType?: ApiComponents['schemas']['AccountTypeEnum'];
      role?: ApiComponents['schemas']['RoleEnum'];
    };
    PatchedUserPreferencesRequest: {
      displayCurrency?: ApiComponents['schemas']['DisplayCurrencyEnum'];
      selectedPortfolio?: string | null;
      theme?: ApiComponents['schemas']['ThemeEnum'];
    };
    PatchedUserProfileRequest: {
      citizenshipCountry?: string;
      confirmedAustralianResident?: boolean;
      confirmedIndividualAccount?: boolean;
      confirmedOver18?: boolean;
      dateOfBirth?: string | null;
      fullName?: string | null;
      isSignupCompleted?: boolean;
      phoneCountryCode?: string | null;
      phoneNumber?: string | null;
      residenceCountry?: string;
      residentialAddress?: string | null;
      termsAndConditions?: boolean;
    };
    PatchedWalletRequest: {
      address?: string;
      addressIndex?: number | null;
      chain?: ApiComponents['schemas']['SupportedWalletChainEnum'];
      derivationPath?: string | null;
      masterFingerprint?: string | null;
      name?: string | null;
      parentChainCode?: string | null;
      parentDerivationPath?: string | null;
      parentPublicKey?: string | null;
      signingPreference?:
        (ApiComponents['schemas']['WalletSigningPreferenceEnum'] | ApiComponents['schemas']['NullEnum']) | null;
      walletType?:
        (ApiComponents['schemas']['WalletSigningPreferenceEnum'] | ApiComponents['schemas']['NullEnum']) | null;
    };
    PauseSubmission: {
      completedAt: string | null;
      paused: boolean;
      status: ApiComponents['schemas']['PauseSubmissionStatusEnum'];
      uuid: string;
    };
    PauseSubmissionRequestRequest: {
      submissionId: string;
    };
    PauseSubmissionResponse: {
      message: string;
      submission: ApiComponents['schemas']['PauseSubmission'];
      token: ApiComponents['schemas']['ShareTokenDetail'];
    };
    PauseSubmissionStatusEnum: 'pending' | 'executing' | 'observed' | 'confirmed' | 'failed';
    PaymentInstruction: {
      amountDue: string;
      assetSymbol?: string;
      bankAccountName?: string;
      bankAccountNumber?: string;
      bankBsb?: string;
      chain?: string;
      contractAddress?: string;
      currency: string;
      decimals?: number;
      issuedAt: string | null;
      payee: string;
      paymentDueAt: string | null;
      rail: ApiComponents['schemas']['SettlementRailEnum'];
      railDisplay: string;
      receivingWalletAddress?: string;
      reference: string;
      settlementAmount?: string;
    };
    PendingTransfer: {
      holdingQuantity: string;
      status: string;
      transactionId: string;
      txHash: string;
    };
    PlatformEnum: 'all' | 'ios' | 'android' | 'web' | 'mobile';
    Portfolio: {
      createdAt: string;
      isActive?: boolean;
      name: string;
      updatedAt: string;
      userAccount: string;
      uuid: string;
      walletCount: number;
      walletUuids: string[];
    };
    PortfolioChainValue: {
      chain: string;
      marketValue?: string;
      quantity: string;
      wallets: string[];
    };
    PortfolioHoldingValue: {
      assetUuid: string;
      marketValue?: string;
      perChain: ApiComponents['schemas']['PortfolioChainValue'][];
      price?: string;
      quantity: string;
      wallets: string[];
    };
    PortfolioRequest: {
      isActive?: boolean;
      name: string;
    };
    PortfolioValuePoint: {
      accountId: string;
      createdAt: string;
      hasValueData: boolean;
      holdingsData: {
        [key: string]: ApiComponents['schemas']['PortfolioHoldingValue'];
      };
      portfolio: string;
      portfolioName: string;
      snapshotDate: string;
      snapshotReason: string;
      totalMarketValue: string | null;
      updatedAt: string;
      uuid: string;
    };
    PortfolioWalletResponse: {
      message: string;
      portfolio: ApiComponents['schemas']['Portfolio'];
      success: boolean;
    };
    PreparedBitcoinTransfer: {
      amountBtc: string;
      amountSatoshis: number;
      estimatedTxSize: number;
      feeBtc: string;
      feePerByte: string;
      feeSatoshis: number;
      fromAddress: string;
      network: ApiComponents['schemas']['NetworkEnum'];
      toAddress: string;
      totalCostBtc: string;
    };
    PreparedEvmTransaction: {
      chainId: number;
      data?: string;
      gas: number;
      gasPrice: number;
      nonce: number;
      to: string;
      value: number;
    };
    PreparedEvmTransfer: {
      amountEth?: string;
      amountToken?: string;
      fromAddress: string;
      gasCostEth: string;
      gasLimit: number;
      gasPriceGwei: string;
      gasPriceWei: string;
      toAddress: string;
      tokenContract?: string;
      tokenDecimals?: number;
      tokenSymbol?: string;
      totalCostEth?: string;
      transaction: ApiComponents['schemas']['PreparedEvmTransaction'];
    };
    PreparedTokenTransaction: {
      chainId: number;
      data: string;
      gas: number;
      gasPrice: number;
      nonce: number;
      to: string;
      value: number;
    };
    PreparedTokenTransfer: {
      amount: number;
      fromAddress: string;
      toAddress: string;
      token: ApiComponents['schemas']['TransferTokenInfo'];
      transactionData: ApiComponents['schemas']['PreparedTokenTransaction'];
    };
    PreparedWalletTransfer:
      ApiComponents['schemas']['PreparedEvmTransfer'] | ApiComponents['schemas']['PreparedBitcoinTransfer'];
    PrepareTransferRequest: {
      amount: number;
      fromAddress: string;
      toAddress: string;
      token: string;
    };
    PrepareWalletTransferRequest: {
      amountBtc?: string;
      amountEth?: string;
      amountToken?: string;
      toAddress: string;
      tokenContract?: string;
    };
    PriceCurrencyEnum: 'AUD' | 'USD' | 'EUR' | 'GBP' | 'CAD' | 'JPY' | 'NZD' | 'SGD';
    PrimaryTypeEnum: 'SwapOrder';
    ProtocolVersionEnum: 1;
    RegisterDeviceTokenRequest: {
      deviceType: ApiComponents['schemas']['DeviceTypeEnum'];
      pushToken: string;
    };
    ResendVerificationRequest: {
      email?: string;
    };
    ReviewResultEnum: 'GREEN' | 'RED' | 'YELLOW';
    RoleEnum: 'investor' | 'company' | 'both';
    SelectedPortfolio: {
      isActive: boolean;
      name: string;
      userAccount: string;
      uuid: string;
    };
    SettlementApprovalBroadcastRequest: {
      ownerAccountUuid: string;
      settlementDigest: string;
      signedTransaction: string;
      swapUuid: string;
      walletUuid: string;
    };
    SettlementApprovalReceipt: {
      blockNumber: number | null;
      gasUsed: number | null;
      orderUuid: string;
      ownerAccountUuid: string;
      settlementDigest: string;
      swapUuid: string;
      txHash: string;
      userRole: ApiComponents['schemas']['UserRoleEnum'];
      walletUuid: string;
    };
    SettlementApprovalStatus: {
      currentAllowance: string;
      needsApproval: boolean;
      orderUuid: string;
      ownerAccountUuid: string;
      requiredAmount: string;
      settlementDigest: string;
      spender: string;
      swapUuid: string;
      tokenAddress: string;
      tokenSymbol: string;
      userRole: ApiComponents['schemas']['UserRoleEnum'];
      walletUuid: string;
    };
    SettlementApprovalTransaction: {
      amount: string;
      description: string;
      needsApproval: ApiComponents['schemas']['ApprovalRequiredEnum'];
      orderUuid: string;
      ownerAccountUuid: string;
      settlementDigest: string;
      spender: string;
      swapUuid: string;
      tokenAddress: string;
      tokenSymbol: string;
      transaction: ApiComponents['schemas']['ApprovalTransaction'];
      unlimited: ApiComponents['schemas']['ApprovalRequiredEnum'];
      userRole: ApiComponents['schemas']['UserRoleEnum'];
      walletUuid: string;
    };
    SettlementApprovalUncertain: {
      code: ApiComponents['schemas']['SettlementApprovalUncertainCodeEnum'];
      detail: string;
      orderUuid: string;
      ownerAccountUuid: string;
      settlementDigest: string;
      swapUuid: string;
      txHash: string;
      userRole: ApiComponents['schemas']['UserRoleEnum'];
      walletUuid: string;
    };
    SettlementApprovalUncertainCodeEnum: 'swap_approval_unconfirmed';
    SettlementAsset: {
      chainDeployments: ApiComponents['schemas']['AssetChainDeployment'][];
      name: string;
      symbol: string;
      uuid: string;
    };
    SettlementContext: {
      buyer: ApiComponents['schemas']['SettlementParty'];
      digest: string;
      orderHash: string;
      paymentAsset: ApiComponents['schemas']['SettlementPaymentAsset'];
      pricePerShare: string;
      protocolVersion: ApiComponents['schemas']['ProtocolVersionEnum'];
      seller: ApiComponents['schemas']['SettlementParty'];
      shareToken: ApiComponents['schemas']['SettlementShareToken'];
      swapUuid: string;
      typedData: ApiComponents['schemas']['SettlementTypedData'];
    };
    SettlementDomain: {
      chainId: string;
      name: ApiComponents['schemas']['NameEnum'];
      verifyingContract: string;
      version: ApiComponents['schemas']['VersionEnum'];
    };
    SettlementParty: {
      address: string;
      orderUuid: string;
      ownerAccountUuid: string;
      paymentAssetUuid: string | null;
      walletUuid: string;
    };
    SettlementPaymentAsset: {
      deploymentAddress: string;
      deploymentChain: string;
      deploymentDecimals: number;
      deploymentUuid: string;
      name: string;
      pricingDecimals: number;
      symbol: string;
      uuid: string;
    };
    SettlementRailEnum: 'bank_transfer' | 'stablecoin';
    SettlementShareToken: {
      address: string;
      chain: string;
      decimals: number;
      name: string;
      symbol: string;
      uuid: string;
    };
    SettlementSignatureRequest: {
      ownerAccountUuid: string;
      settlementDigest: string;
      signature: string;
      signerAddress: string;
      swapUuid: string;
      walletUuid: string;
    };
    SettlementSufficientApproval: {
      currentAllowance: string;
      message: string;
      needsApproval: ApiComponents['schemas']['ApprovalSufficientEnum'];
      orderUuid: string;
      ownerAccountUuid: string;
      requiredAmount: string;
      settlementDigest: string;
      swapUuid: string;
      userRole: ApiComponents['schemas']['UserRoleEnum'];
      walletUuid: string;
    };
    SettlementSwapOrder: {
      buyerAddress: string;
      buyerHasSigned: boolean;
      buyOrderUuid: string;
      completedAt: string | null;
      createdAt: string;
      errorMessage: string;
      expiresAt: string;
      isExpired: boolean;
      isReady: boolean;
      nonce: number;
      orderHash: string;
      paymentAmount: number;
      paymentTokenAddress: string;
      paymentTokenSymbol: string;
      sellerAddress: string;
      sellerHasSigned: boolean;
      sellOrderUuid: string;
      settlementContext: ApiComponents['schemas']['SettlementContext'];
      settlementDigest: string;
      settlementProtocolVersion: ApiComponents['schemas']['ProtocolVersionEnum'];
      shareAmount: number;
      shareTokenAddress: string;
      shareTokenName: string;
      shareTokenSymbol: string;
      status: ApiComponents['schemas']['SwapOrderStatusEnum'];
      statusDisplay: string;
      txHash: string;
      updatedAt: string;
      uuid: string;
    };
    SettlementSwapOrderForSigning: {
      admissionRefusal: string | null;
      canSign: boolean;
      hasSigned: boolean;
      orderUuid: string;
      ownerAccountUuid: string;
      settlementDigest: string;
      swapOrder: ApiComponents['schemas']['SettlementSwapOrder'];
      swapUuid: string;
      typedData: ApiComponents['schemas']['SettlementTypedData'];
      userRole: ApiComponents['schemas']['UserRoleEnum'];
      walletUuid: string;
    };
    SettlementTypedData: {
      domain: ApiComponents['schemas']['SettlementDomain'];
      message: ApiComponents['schemas']['SwapMessage'];
      primaryType: ApiComponents['schemas']['PrimaryTypeEnum'];
      types: ApiComponents['schemas']['SwapSigningTypes'];
    };
    ShareIssuanceCreateRequest: {
      amount: number;
      issuanceType?: ApiComponents['schemas']['IssuanceTypeEnum'];
      reason?: string;
      recipient: string;
    };
    ShareIssuanceList: {
      amount: string;
      blockNumber: number | null;
      completedAt: string | null;
      createdAt: string;
      initiatedBy: number | null;
      initiatedByEmail: string | null;
      issuanceType: ApiComponents['schemas']['IssuanceTypeEnum'];
      issuanceTypeDisplay: string;
      processedAt: string | null;
      reason: string;
      recipientAddress: string;
      recipientName: string;
      status: ApiComponents['schemas']['ShareIssuanceListStatusEnum'];
      statusDisplay: string;
      subscriptionReference: string | null;
      token: string;
      tokenSymbol: string;
      txHash: string | null;
      uuid: string;
    };
    ShareIssuanceListStatusEnum: 'pending' | 'processing' | 'completed' | 'failed';
    ShareIssuanceRequest: {
      amount: number;
      createdAt: string;
      dilutionPercentage: string | null;
      executedAt: string | null;
      executedIssuance: string | null;
      executionNotes: string;
      issuanceType: ApiComponents['schemas']['IssuanceTypeEnum'];
      issuanceTypeDisplay: string;
      reason: string;
      recipientAddress: string;
      recipientName: string;
      rejectionReason: string;
      reviewedAt: string | null;
      reviewedBy: number | null;
      reviewedByEmail: string | null;
      status: ApiComponents['schemas']['CapitalRequestStatusEnum'];
      statusDisplay: string;
      submittedAt: string | null;
      submittedBy: number | null;
      submittedByEmail: string | null;
      token: string;
      tokenName: string;
      tokenSymbol: string;
      updatedAt: string;
      uuid: string;
    };
    ShareIssuanceRequested: {
      issuanceRequest: ApiComponents['schemas']['ShareIssuanceRequest'];
      message: string;
      token: ApiComponents['schemas']['ShareTokenDetail'];
    };
    ShareRegister: {
      discrepancy: string;
      formerMembers: ApiComponents['schemas']['FormerMember'][];
      formerMembersAsAt: string | null;
      formerMembersBlock: number | null;
      formerMembersStale: boolean;
      holders: ApiComponents['schemas']['ShareRegisterHolder'][];
      issuedSupply: string;
      listedTotal: string;
      token: ApiComponents['schemas']['ShareRegisterToken'];
      totalHolders: number;
    };
    ShareRegisterHolder: {
      address: string;
      balance: string;
      enteredOn: string | null;
      holderType: ApiComponents['schemas']['HolderTypeEnum'];
      identitySource: string;
      name: string | null;
      percentage: number;
      shareClass: string;
      source: string;
    };
    ShareRegisterToken: {
      name: string;
      status: string;
      symbol: string;
      totalSupply: string;
      uuid: string;
    };
    ShareTokenCreateRequest: {
      company?: string;
      decimals?: number;
      isDivisible?: boolean;
      isTransferable?: boolean;
      name: string;
      symbol: string;
      tokenType?: ApiComponents['schemas']['TokenTypeEnum'];
      totalSupply: string;
    };
    ShareTokenDetail: {
      chain: string | null;
      company: string;
      companyName: string;
      companyUuid: string;
      contractAddress: string | null;
      createdAt: string;
      decimals: number;
      deployedAt: string | null;
      deploymentTxHash: string | null;
      isDivisible: boolean;
      isTransferable: boolean;
      name: string;
      status: ApiComponents['schemas']['ShareTokenStatusEnum'];
      statusDisplay: string;
      symbol: string;
      tokenType: ApiComponents['schemas']['TokenTypeEnum'];
      tokenTypeDisplay: string;
      totalSupply: string;
      updatedAt: string;
      uuid: string;
    };
    ShareTokenList: {
      bestAsk: string | null;
      bestBid: string | null;
      chain: string | null;
      company: string;
      companyName: string;
      companyUuid: string;
      contractAddress: string | null;
      createdAt: string;
      decimals: number;
      deployedAt: string | null;
      isDivisible: boolean;
      isTransferable: boolean;
      lastPrice: string | null;
      name: string;
      status: ApiComponents['schemas']['ShareTokenStatusEnum'];
      statusDisplay: string;
      symbol: string;
      tokenType: ApiComponents['schemas']['TokenTypeEnum'];
      tokenTypeDisplay: string;
      totalSupply: string;
      uuid: string;
    };
    ShareTokenStatusEnum: 'draft' | 'deploying' | 'deployed' | 'paused';
    SignedOrderSubmissionRequest: {
      digest?: string;
      minQuantity?: number | string;
      orderType: ApiComponents['schemas']['TransferOrderTypeEnum'];
      ownerAccountUuid: string;
      pricePerShare: string;
      quantity: number | string;
      signature?: string;
      submissionId: string;
      token: string;
      walletAddress: string;
      walletUuid: string;
    };
    SigningDomain: {
      chainId: number;
      name: string;
      verifyingContract: string;
      version: string;
    };
    SigningMessage: {
      [key: string]: string;
    };
    SigningType: {
      name: string;
      type: string;
    };
    SigningTypes: {
      [key: string]: {
        name: string;
        type: string;
      }[];
    };
    SubmissionOrder: {
      canBeModified: boolean;
      completedAt: string | null;
      createdAt: string;
      errorMessage: string;
      filledQuantity: number;
      lastModifiedAt: string | null;
      matchedOrderUuid: string | null;
      minQuantity: number;
      modificationCount: number;
      orderType: ApiComponents['schemas']['TransferOrderTypeEnum'];
      orderTypeDisplay: string;
      pricePerShare: string;
      quantity: number;
      remainingQuantity: number;
      remainingValue: string;
      status: ApiComponents['schemas']['TransferOrderStatusEnum'];
      statusDisplay: string;
      token: string;
      tokenContractAddress: string;
      tokenName: string;
      tokenSymbol: string;
      totalValue: string;
      txHash: string;
      updatedAt: string;
      uuid: string;
      walletAddress: string;
    };
    SubscriptionCreateRequest: {
      offering: string;
      quantity: number;
      wallet: string;
    };
    SubscriptionDetail: {
      allottedQuantity: number | null;
      amountDue: string;
      amountOutstanding: string;
      amountReceived: string | null;
      companyName: string;
      createdAt: string;
      offeringUuid: string;
      paymentDueAt: string | null;
      paymentInstruction: ApiComponents['schemas']['PaymentInstruction'] | null;
      paymentInstructionIssuedAt: string | null;
      paymentNotes: string;
      paymentReceivedOn: string | null;
      paymentReferenceSeen: string;
      paymentTxHash: string;
      pricePerShare: string;
      quantity: number;
      reference: string;
      refundAmount: string | null;
      refundedAt: string | null;
      refundReference: string;
      settlementAmount: number | null;
      settlementAssetSymbol: string | null;
      settlementRail: ApiComponents['schemas']['SettlementRailEnum'];
      settlementRailDisplay: string;
      status: ApiComponents['schemas']['SubscriptionStatusEnum'];
      statusDisplay: string;
      tokenName: string;
      tokenSymbol: string;
      updatedAt: string;
      uuid: string;
      walletAddress: string;
    };
    SubscriptionList: {
      allottedQuantity: number | null;
      amountDue: string;
      amountReceived: string | null;
      companyName: string;
      createdAt: string;
      offeringUuid: string;
      paymentDueAt: string | null;
      pricePerShare: string;
      quantity: number;
      reference: string;
      settlementRail: ApiComponents['schemas']['SettlementRailEnum'];
      settlementRailDisplay: string;
      status: ApiComponents['schemas']['SubscriptionStatusEnum'];
      statusDisplay: string;
      tokenName: string;
      tokenSymbol: string;
      uuid: string;
      walletAddress: string;
    };
    SubscriptionStatusEnum:
      | 'draft'
      | 'submitted'
      | 'accepted'
      | 'awaiting_payment'
      | 'paid'
      | 'allotted'
      | 'rejected'
      | 'withdrawn'
      | 'refunded';
    SubscriptionWithdrawRequest: {
      reason?: string;
    };
    SupportedWalletChainEnum: 'base' | 'bitcoin' | 'ethereum';
    SwapMessage: {
      buyer: string;
      deadline: string;
      nonce: string;
      paymentAmount: string;
      paymentToken: string;
      seller: string;
      shareAmount: string;
      shareToken: string;
    };
    SwapOrderList: {
      buyerAddress: string;
      buyerHasSigned: boolean;
      buyOrderUuid: string;
      createdAt: string;
      expiresAt: string;
      paymentAmount: number;
      paymentTokenSymbol: string;
      sellerAddress: string;
      sellerHasSigned: boolean;
      sellOrderUuid: string;
      settlementProtocolVersion: number;
      shareAmount: number;
      shareTokenName: string;
      shareTokenSymbol: string;
      status: ApiComponents['schemas']['SwapOrderStatusEnum'];
      statusDisplay: string;
      uuid: string;
    };
    SwapOrderStatusEnum:
      'created' | 'seller_signed' | 'buyer_signed' | 'ready' | 'executing' | 'completed' | 'failed' | 'expired';
    SwapSigningTypes: {
      EIP712Domain: ApiComponents['schemas']['SigningType'][];
      SwapOrder: ApiComponents['schemas']['SigningType'][];
    };
    ThemeEnum: 'dark' | 'light';
    TokenDeploymentStarted: {
      message: string;
      token: ApiComponents['schemas']['ShareTokenDetail'];
    };
    TokenTransferReceipt: {
      blockNumber: number | null;
      gasUsed: number | null;
      txHash: string;
    };
    TokenTypeEnum: 'ordinary' | 'preference' | 'redeemable';
    ToStatusEnum: 'cancelled';
    TradingBroadcastTransferRequest: {
      signedTransaction: string;
    };
    TradingWalletBalances: {
      balances: ApiComponents['schemas']['TradingWalletTokenBalance'][];
      walletAddress: string;
    };
    TradingWalletTokenBalance: {
      balance: string;
      contractAddress: string;
      decimals: number;
      name: string;
      symbol: string;
      token: string;
      type: ApiComponents['schemas']['TypeEnum'];
    };
    Transaction: {
      amount: string;
      asset: string;
      assetName: string;
      assetSymbol: string;
      blockNumber: number | null;
      blockTimestamp: string | null;
      chain: ApiComponents['schemas']['TransactionChainEnum'];
      createdAt: string;
      fromAddress: string;
      marketValue: string | null;
      status: ApiComponents['schemas']['TransactionStatusEnum'];
      toAddress: string | null;
      transactionFee: string | null;
      transactionFeeEstimated: string | null;
      txHash: string;
      uuid: string;
      wallet: string;
      walletAddress: string;
    };
    TransactionChainEnum:
      'ethereum' | 'bitcoin' | 'polygon' | 'solana' | 'avalanche' | 'arbitrum' | 'optimism' | 'base';
    TransactionStatusEnum: 'pending' | 'confirmed' | 'failed' | 'reorged' | 'replaced';
    TransferOrderCreateRequest: {
      minQuantity?: number | string;
      orderType: ApiComponents['schemas']['TransferOrderTypeEnum'];
      ownerAccountUuid: string;
      pricePerShare: string;
      quantity: number | string;
      submissionId: string;
      token: string;
      walletAddress: string;
      walletUuid: string;
    };
    TransferOrderDetail: {
      canBeModified: boolean;
      completedAt: string | null;
      createdAt: string;
      errorMessage: string;
      filledQuantity: number;
      lastModifiedAt: string | null;
      matchedOrderUuid: string | null;
      minQuantity: number;
      modificationCount: number;
      orderType: ApiComponents['schemas']['TransferOrderTypeEnum'];
      orderTypeDisplay: string;
      pricePerShare: string;
      quantity: number;
      remainingQuantity: number;
      remainingValue: string;
      status: ApiComponents['schemas']['TransferOrderStatusEnum'];
      statusDisplay: string;
      token: string;
      tokenContractAddress: string;
      tokenName: string;
      tokenSymbol: string;
      totalValue: string;
      txHash: string;
      updatedAt: string;
      uuid: string;
      walletAddress: string;
    };
    TransferOrderList: {
      createdAt: string;
      filledQuantity: number;
      minQuantity: number;
      orderType: ApiComponents['schemas']['TransferOrderTypeEnum'];
      orderTypeDisplay: string;
      pricePerShare: string;
      quantity: number;
      remainingQuantity: number;
      status: ApiComponents['schemas']['TransferOrderStatusEnum'];
      statusDisplay: string;
      token: string;
      tokenName: string;
      tokenSymbol: string;
      totalValue: string;
      uuid: string;
      walletAddress: string;
    };
    TransferOrderStatusEnum:
      | 'open'
      | 'partially_filled'
      | 'matched'
      | 'pending_signature'
      | 'executing'
      | 'completed'
      | 'cancelled'
      | 'expired'
      | 'failed';
    TransferOrderTypeEnum: 'buy' | 'sell';
    TransferTokenInfo: {
      contractAddress: string;
      symbol: string;
      uuid: string;
    };
    TypeEnum: 'share_token' | 'stablecoin';
    UnreadCountResponse: {
      unreadCount: number;
    };
    UnregisterDeviceTokenRequest: {
      pushToken: string;
    };
    UserAccount: {
      accountNumber: string;
      accountType?: ApiComponents['schemas']['AccountTypeEnum'];
      activationDate: string | null;
      role?: ApiComponents['schemas']['RoleEnum'];
      uuid: string;
    };
    UserDocumentTypeEnum: 'payslip' | 'bank_statement' | 'tax_return' | 'other';
    UserPreferences: {
      displayCurrency?: ApiComponents['schemas']['DisplayCurrencyEnum'];
      selectedPortfolio: ApiComponents['schemas']['SelectedPortfolio'] | null;
      theme?: ApiComponents['schemas']['ThemeEnum'];
      userAccount: ApiComponents['schemas']['AccountSummary'] | null;
      userProfile: string;
      uuid: string;
    };
    UserPreferencesRequest: {
      displayCurrency?: ApiComponents['schemas']['DisplayCurrencyEnum'];
      selectedPortfolio?: string | null;
      theme?: ApiComponents['schemas']['ThemeEnum'];
    };
    UserProfile: {
      citizenshipCountry: string | null;
      citizenshipCountryName: string | null;
      confirmedAustralianResident?: boolean;
      confirmedIndividualAccount?: boolean;
      confirmedOver18?: boolean;
      dateJoined: string;
      dateOfBirth?: string | null;
      email: string;
      fullName?: string | null;
      isActive: boolean;
      isIdVerified: boolean;
      isSignupCompleted?: boolean;
      isStaff: boolean;
      kycaidApplicantId: string | null;
      kycProvider: ApiComponents['schemas']['KycProviderEnum'];
      lastLogin: string | null;
      phoneCountryCode?: string | null;
      phoneNumber?: string | null;
      rejectionLabels: string[] | null;
      residenceCountry?: string | null;
      residenceCountryName: string | null;
      residentialAddress?: string | null;
      reviewResult: (ApiComponents['schemas']['ReviewResultEnum'] | ApiComponents['schemas']['NullEnum']) | null;
      sumsubApplicantId: string | null;
      sumsubVerificationStatus:
        (ApiComponents['schemas']['UserVerificationStatusEnum'] | ApiComponents['schemas']['NullEnum']) | null;
      termsAndConditions?: boolean;
      uuid: string;
      verificationStatus:
        (ApiComponents['schemas']['UserVerificationStatusEnum'] | ApiComponents['schemas']['NullEnum']) | null;
      verifiedAt: string | null;
    };
    UserProfileRequest: {
      citizenshipCountry: string;
      confirmedAustralianResident?: boolean;
      confirmedIndividualAccount?: boolean;
      confirmedOver18?: boolean;
      dateOfBirth?: string | null;
      fullName?: string | null;
      isSignupCompleted?: boolean;
      phoneCountryCode?: string | null;
      phoneNumber?: string | null;
      residenceCountry?: string;
      residentialAddress?: string | null;
      termsAndConditions?: boolean;
    };
    UserRoleEnum: 'buyer' | 'seller';
    UserSigninRequest: {
      email: string;
      password: string;
    };
    UserSignupRequest: {
      email: string;
      password: string;
      passwordConfirm: string;
    };
    UserVerificationStatusEnum: 'init' | 'pending' | 'queued' | 'completed' | 'onHold' | 'prechecked';
    ValueSourceEnum: 'market' | 'nav' | 'par' | 'unpriced';
    VersionEnum: '1';
    Wallet: {
      address: string;
      addressIndex?: number | null;
      chain: ApiComponents['schemas']['SupportedWalletChainEnum'];
      createdAt: string;
      derivationPath?: string | null;
      lastSyncedAt: string | null;
      marketValue: string;
      masterFingerprint?: string | null;
      name?: string | null;
      nativeBalance: string;
      nativeMarketValue: string;
      parentChainCode?: string | null;
      parentDerivationPath?: string | null;
      parentPublicKey?: string | null;
      signingPreference?:
        (ApiComponents['schemas']['WalletSigningPreferenceEnum'] | ApiComponents['schemas']['NullEnum']) | null;
      updatedAt: string;
      userAccount: string;
      uuid: string;
      verificationChallenge: string | null;
      verificationSignature: string | null;
      verificationStatus: ApiComponents['schemas']['WalletVerificationStatusEnum'];
      verifiedAt: string | null;
      walletType?:
        (ApiComponents['schemas']['WalletSigningPreferenceEnum'] | ApiComponents['schemas']['NullEnum']) | null;
    };
    WalletRequest: {
      address: string;
      addressIndex?: number | null;
      chain: ApiComponents['schemas']['SupportedWalletChainEnum'];
      derivationPath?: string | null;
      masterFingerprint?: string | null;
      name?: string | null;
      parentChainCode?: string | null;
      parentDerivationPath?: string | null;
      parentPublicKey?: string | null;
      signingPreference?:
        (ApiComponents['schemas']['WalletSigningPreferenceEnum'] | ApiComponents['schemas']['NullEnum']) | null;
      walletType?:
        (ApiComponents['schemas']['WalletSigningPreferenceEnum'] | ApiComponents['schemas']['NullEnum']) | null;
    };
    WalletSigningPreferenceEnum: 'hardware' | 'software';
    WalletSyncResponse: {
      success: boolean;
      syncResult: ApiComponents['schemas']['WalletSyncResult'];
      wallet: ApiComponents['schemas']['Wallet'];
    };
    WalletSyncResult: {
      error?: string;
      holdings?: number;
      snapshots?: number;
      status: ApiComponents['schemas']['WalletSyncResultStatusEnum'];
      transactions?: number;
    };
    WalletSyncResultStatusEnum: 'success' | 'skipped' | 'error';
    WalletVerificationChallenge: {
      challenge: string;
      message: string;
      walletAddress: string;
    };
    WalletVerificationResult: {
      message: string;
      success: boolean;
      verificationStatus: ApiComponents['schemas']['WalletVerificationResultVerificationStatusEnum'];
      verifiedAt: string;
    };
    WalletVerificationResultVerificationStatusEnum: 'PENDING' | 'VERIFIED';
    WalletVerificationSignatureRequest: {
      signature: string;
    };
    WalletVerificationStatusEnum: 'PENDING' | 'VERIFIED';
    WhitelistAddRequest: {
      submissionId: string;
      walletAddress: string;
    };
    WhitelistBatchAddRequest: {
      entries: ApiComponents['schemas']['WhitelistAddRequest'][];
    };
    WhitelistBatchError: {
      error: string;
      walletAddress: string;
    };
    WhitelistBatchResponse: {
      errors: ApiComponents['schemas']['WhitelistBatchError'][];
      failed: number;
      pending: number;
      results: ApiComponents['schemas']['WhitelistChange'][];
      successful: number;
    };
    WhitelistChange: {
      action: ApiComponents['schemas']['ActionEnum'];
      entry: ApiComponents['schemas']['WhitelistEntry'] | null;
      message: string;
      status?: ApiComponents['schemas']['WhitelistChangeStatusEnum'];
      submissionId: string;
      success: boolean;
      txHash?: string | null;
      walletAddress: string;
    };
    WhitelistChangeStatusEnum: 'pending' | 'executing' | 'confirmed' | 'unchanged' | 'failed';
    WhitelistEntry: {
      addTxHash: string | null;
      createdAt: string;
      isWhitelisted: boolean;
      label: string;
      lastSyncedAt: string | null;
      onChainTimestamp: string | null;
      removeTxHash: string | null;
      status: ApiComponents['schemas']['WhitelistEntryStatusEnum'];
      statusDisplay: string;
      updatedAt: string;
      uuid: string;
      walletAddress: string;
    };
    WhitelistEntryStatusEnum: 'pending' | 'active' | 'removed' | 'failed';
    WhitelistRemoveRequest: {
      submissionId: string;
      walletAddress: string;
    };
    WhitelistStatus: {
      address: string;
      canReceive: boolean;
      isWhitelisted: boolean;
      status: ApiComponents['schemas']['WhitelistStatusStatusEnum'];
    };
    WhitelistStatusStatusEnum: 'whitelisted' | 'not_whitelisted' | 'unknown';
    WhitelistSyncResponse: {
      entry: ApiComponents['schemas']['WhitelistEntry'];
      message: string;
      success: boolean;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type ApiDefs = Record<string, never>;
export interface ApiOperations {
  api_assets_list: {
    parameters: {
      query?: {
        asset_type?: string;
        chain?: string;
        is_active?: boolean;
        ordering?: string;
        page?: number;
        search?: string;
        symbol?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedAssetList'];
        };
      };
    };
  };
  api_assets_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Asset'];
        };
      };
    };
  };
  api_assets_snapshots_list: {
    parameters: {
      query?: {
        end_date?: string;
        max_points?: number;
        order_by?: '-source_timestamp' | 'source_timestamp';
        start_date?: string;
      };
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AssetSnapshot'][];
        };
      };
    };
  };
  api_assets_exchange_rates_retrieve: {
    parameters: {
      query?: {
        currency?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ExchangeRateResponse'];
        };
      };
    };
  };
  api_auth_verify_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthSessionValidity'];
        };
      };
    };
  };
  api_change_password_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['ChangePasswordRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['ChangePasswordRequest'];
        'multipart/form-data': ApiComponents['schemas']['ChangePasswordRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthPasswordChanged'];
        };
      };
    };
  };
  api_device_tokens_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedDeviceTokenList'];
        };
      };
    };
  };
  api_device_tokens_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['DeviceTokenRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['DeviceTokenRequest'];
        'multipart/form-data': ApiComponents['schemas']['DeviceTokenRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['DeviceToken'];
        };
      };
    };
  };
  api_device_tokens_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['DeviceToken'];
        };
      };
    };
  };
  api_device_tokens_register_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['RegisterDeviceTokenRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['RegisterDeviceTokenRequest'];
        'multipart/form-data': ApiComponents['schemas']['RegisterDeviceTokenRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['DeviceToken'];
        };
      };
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['DeviceToken'];
        };
      };
    };
  };
  api_device_tokens_unregister_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['UnregisterDeviceTokenRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['UnregisterDeviceTokenRequest'];
        'multipart/form-data': ApiComponents['schemas']['UnregisterDeviceTokenRequest'];
      };
    };
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['DeviceTokenNotFound'];
        };
      };
    };
  };
  api_email_verification_create: {
    parameters: {
      query?: never;
      header?: {
        'X-Auth-Transport'?: string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['EmailVerificationRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['EmailVerificationRequest'];
        'multipart/form-data': ApiComponents['schemas']['EmailVerificationRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthEmailVerified'];
        };
      };
    };
  };
  api_favourite_assets_list: {
    parameters: {
      query?: {
        asset?: string;
        asset_symbol?: string;
        date_from?: string;
        date_to?: string;
        ordering?: string;
        page?: number;
        user_account?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedFavouriteAssetList'];
        };
      };
    };
  };
  api_favourite_assets_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['FavouriteAssetRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['FavouriteAssetRequest'];
        'multipart/form-data': ApiComponents['schemas']['FavouriteAssetRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['FavouriteAsset'];
        };
      };
    };
  };
  api_favourite_assets_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['FavouriteAsset'];
        };
      };
    };
  };
  api_favourite_assets_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_feature_flags_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedFeatureFlagList'];
        };
      };
    };
  };
  api_feature_flags_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['FeatureFlag'];
        };
      };
    };
  };
  api_fiat_purchases_transak_widget_url_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['FiatPurchaseWidgetRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['FiatPurchaseWidgetRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['FiatPurchaseWidgetRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['FiatPurchaseWidget'];
        };
      };
    };
  };
  api_financial_profiles_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedFinancialProfileList'];
        };
      };
    };
  };
  api_financial_profiles_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['FinancialProfileRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['FinancialProfileRequest'];
        'multipart/form-data': ApiComponents['schemas']['FinancialProfileRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['FinancialProfile'];
        };
      };
    };
  };
  api_financial_profiles_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['FinancialProfile'];
        };
      };
    };
  };
  api_financial_profiles_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['FinancialProfileRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['FinancialProfileRequest'];
        'multipart/form-data': ApiComponents['schemas']['FinancialProfileRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['FinancialProfile'];
        };
      };
    };
  };
  api_financial_profiles_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedFinancialProfileRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedFinancialProfileRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedFinancialProfileRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['FinancialProfile'];
        };
      };
    };
  };
  api_investor_classifications_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedInvestorClassificationList'];
        };
      };
    };
  };
  api_investor_classifications_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['InvestorClassificationRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['InvestorClassificationRequest'];
        'multipart/form-data': ApiComponents['schemas']['InvestorClassificationRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['InvestorClassification'];
        };
      };
    };
  };
  api_investor_classifications_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['InvestorClassification'];
        };
      };
    };
  };
  api_investor_classifications_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_investor_classifications_evidence_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          '*/*': Blob;
        };
      };
    };
  };
  api_investor_classifications_eligibility_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['InvestorEligibility'];
        };
      };
    };
  };
  api_notification_preferences_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['NotificationPreferences'];
        };
      };
    };
  };
  api_notification_preferences_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['NotificationPreferencesRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['NotificationPreferencesRequest'];
        'multipart/form-data': ApiComponents['schemas']['NotificationPreferencesRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['NotificationPreferences'];
        };
      };
    };
  };
  api_notification_preferences_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['NotificationPreferences'];
        };
      };
    };
  };
  api_notification_preferences_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedNotificationPreferencesRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedNotificationPreferencesRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedNotificationPreferencesRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['NotificationPreferences'];
        };
      };
    };
  };
  api_notifications_list: {
    parameters: {
      query?: {
        is_archived?: boolean;
        is_read?: boolean;
        notification_type?: string;
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedNotificationList'];
        };
      };
    };
  };
  api_notifications_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Notification'];
        };
      };
    };
  };
  api_notifications_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedNotificationRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedNotificationRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedNotificationRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Notification'];
        };
      };
    };
  };
  api_notifications_mark_all_read_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['NotificationRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['NotificationRequest'];
        'multipart/form-data': ApiComponents['schemas']['NotificationRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['MarkAllReadResponse'];
        };
      };
    };
  };
  api_notifications_unread_count_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UnreadCountResponse'];
        };
      };
    };
  };
  api_operator_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Operator'];
        };
      };
    };
  };
  api_portfolios_list: {
    parameters: {
      query?: {
        is_active?: boolean;
        ordering?: string;
        page?: number;
        user_account?: string;
        user_profile?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedPortfolioList'];
        };
      };
    };
  };
  api_portfolios_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['PortfolioRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PortfolioRequest'];
        'multipart/form-data': ApiComponents['schemas']['PortfolioRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Portfolio'];
        };
      };
    };
  };
  api_portfolios_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Portfolio'];
        };
      };
    };
  };
  api_portfolios_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['PortfolioRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PortfolioRequest'];
        'multipart/form-data': ApiComponents['schemas']['PortfolioRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Portfolio'];
        };
      };
    };
  };
  api_portfolios_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_portfolios_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedPortfolioRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedPortfolioRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedPortfolioRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Portfolio'];
        };
      };
    };
  };
  api_portfolios_add_wallet_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['PortfolioRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PortfolioRequest'];
        'multipart/form-data': ApiComponents['schemas']['PortfolioRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PortfolioWalletResponse'];
        };
      };
    };
  };
  api_portfolios_remove_wallet_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['PortfolioRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PortfolioRequest'];
        'multipart/form-data': ApiComponents['schemas']['PortfolioRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PortfolioWalletResponse'];
        };
      };
    };
  };
  api_portfolios_snapshots_list: {
    parameters: {
      query?: {
        end_date?: string;
        max_points?: number;
        order_by?: string;
        start_date?: string;
      };
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PortfolioValuePoint'][];
        };
      };
    };
  };
  api_resend_verification_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['ResendVerificationRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['ResendVerificationRequest'];
        'multipart/form-data': ApiComponents['schemas']['ResendVerificationRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthVerificationResent'];
        };
      };
    };
  };
  api_signin_create: {
    parameters: {
      query?: never;
      header?: {
        'X-Auth-Transport'?: string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['UserSigninRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['UserSigninRequest'];
        'multipart/form-data': ApiComponents['schemas']['UserSigninRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthSession'];
        };
      };
    };
  };
  api_signout_all_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthSignedOutEverywhere'];
        };
      };
    };
  };
  api_signout_create: {
    parameters: {
      query?: never;
      header?: {
        'X-Auth-Transport'?: string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['AuthSignoutRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['AuthSignoutRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['AuthSignoutRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthSignedOut'];
        };
      };
    };
  };
  api_signup_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['UserSignupRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['UserSignupRequest'];
        'multipart/form-data': ApiComponents['schemas']['UserSignupRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthIdentity'];
        };
      };
    };
  };
  api_token_refresh_create: {
    parameters: {
      query?: never;
      header?: {
        'X-Auth-Transport'?: string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['AuthRefreshRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['AuthRefreshRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['AuthRefreshRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthRefreshResponse'];
        };
      };
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthRefreshError'];
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AuthRefreshError'];
        };
      };
    };
  };
  api_transactions_list: {
    parameters: {
      query?: {
        address?: string;
        asset?: string;
        chain?: string;
        direction?: string;
        end_date?: string;
        ordering?: string;
        page?: number;
        start_date?: string;
        wallet?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedTransactionList'];
        };
      };
    };
  };
  api_transactions_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Transaction'];
        };
      };
    };
  };
  api_user_accounts_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserAccount'];
        };
      };
    };
  };
  api_user_accounts_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserAccount'];
        };
      };
    };
  };
  api_user_accounts_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedUserAccountRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedUserAccountRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedUserAccountRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserAccount'];
        };
      };
    };
  };
  api_user_preferences_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserPreferences'];
        };
      };
    };
  };
  api_user_preferences_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['UserPreferencesRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['UserPreferencesRequest'];
        'multipart/form-data': ApiComponents['schemas']['UserPreferencesRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserPreferences'];
        };
      };
    };
  };
  api_user_preferences_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserPreferences'];
        };
      };
    };
  };
  api_user_preferences_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['UserPreferencesRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['UserPreferencesRequest'];
        'multipart/form-data': ApiComponents['schemas']['UserPreferencesRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserPreferences'];
        };
      };
    };
  };
  api_user_preferences_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_user_preferences_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedUserPreferencesRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedUserPreferencesRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedUserPreferencesRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserPreferences'];
        };
      };
    };
  };
  api_user_profiles_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedUserProfileList'];
        };
      };
    };
  };
  api_user_profiles_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['UserProfileRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['UserProfileRequest'];
        'multipart/form-data': ApiComponents['schemas']['UserProfileRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserProfile'];
        };
      };
    };
  };
  api_user_profiles_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserProfile'];
        };
      };
    };
  };
  api_user_profiles_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['UserProfileRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['UserProfileRequest'];
        'multipart/form-data': ApiComponents['schemas']['UserProfileRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserProfile'];
        };
      };
    };
  };
  api_user_profiles_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedUserProfileRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedUserProfileRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedUserProfileRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['UserProfile'];
        };
      };
    };
  };
  api_user_profiles_delete_account_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['UserProfileRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['UserProfileRequest'];
        'multipart/form-data': ApiComponents['schemas']['UserProfileRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['DeletedAccountResponse'];
        };
      };
    };
  };
  api_user_profiles_export_data_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['AccountExportData'];
        };
      };
    };
  };
  api_users_identity_verification_status_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['IdentityVerificationStatus'];
        };
      };
    };
  };
  api_users_identity_verification_token_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['IdentityVerificationSession'];
        };
      };
    };
  };
  api_v1_companies_list: {
    parameters: {
      query?: {
        acn?: string;
        active_only?: boolean;
        company_type?: string;
        ordering?: string;
        page?: number;
        search?: string;
        status?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedCompanyListList'];
        };
      };
    };
  };
  api_v1_companies_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['CompanyRegistrationRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['CompanyRegistrationRequest'];
        'multipart/form-data': ApiComponents['schemas']['CompanyRegistrationRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyRegistered'];
        };
      };
    };
  };
  api_v1_companies_documents_list: {
    parameters: {
      query?: {
        company_uuid?: string;
        document_type?: string;
        is_verified?: boolean;
        ordering?: string;
        page?: number;
      };
      header?: never;
      path: {
        company_uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedCompanyDocumentList'];
        };
      };
    };
  };
  api_v1_companies_documents_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        company_uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['CompanyDocumentRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['CompanyDocumentRequest'];
        'multipart/form-data': ApiComponents['schemas']['CompanyDocumentRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyDocument'];
        };
      };
    };
  };
  api_v1_companies_documents_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        company_uuid: string;
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyDocument'];
        };
      };
    };
  };
  api_v1_companies_documents_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        company_uuid: string;
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_v1_companies_documents_file_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        company_uuid: string;
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          '*/*': Blob;
        };
      };
    };
  };
  api_v1_companies_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyDetail'];
        };
      };
    };
  };
  api_v1_companies_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['CompanyUpdateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['CompanyUpdateRequest'];
        'multipart/form-data': ApiComponents['schemas']['CompanyUpdateRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyUpdate'];
        };
      };
    };
  };
  api_v1_companies_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_v1_companies_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedCompanyUpdateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedCompanyUpdateRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedCompanyUpdateRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyUpdate'];
        };
      };
    };
  };
  api_v1_companies_api_key_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyAPIKey'];
        };
      };
    };
  };
  api_v1_companies_api_key_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyAPIKey'];
        };
      };
    };
  };
  api_v1_companies_application_status_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ApplicationStatus'];
        };
      };
    };
  };
  api_v1_companies_resubmit_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['ApplicationResubmitRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['ApplicationResubmitRequest'];
        'multipart/form-data': ApiComponents['schemas']['ApplicationResubmitRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyApplicationResubmitted'];
        };
      };
    };
  };
  api_v1_companies_stats_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyStats'];
        };
      };
    };
  };
  api_v1_companies_status_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['CompanyStatusUpdateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['CompanyStatusUpdateRequest'];
        'multipart/form-data': ApiComponents['schemas']['CompanyStatusUpdateRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyStatusUpdated'];
        };
      };
    };
  };
  api_v1_companies_submit_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyApplicationSubmitted'];
        };
      };
    };
  };
  api_v1_companies_withdraw_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['ApplicationWithdrawRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['ApplicationWithdrawRequest'];
        'multipart/form-data': ApiComponents['schemas']['ApplicationWithdrawRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CompanyApplicationWithdrawn'];
        };
      };
    };
  };
  api_v1_directory_tokens_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedDirectoryTokenListList'];
        };
      };
    };
  };
  api_v1_directory_tokens_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['DirectoryTokenList'];
        };
      };
    };
  };
  api_v1_documents_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedDocumentList'];
        };
      };
    };
  };
  api_v1_documents_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['DocumentUploadRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['DocumentUploadRequest'];
        'multipart/form-data': ApiComponents['schemas']['DocumentUploadRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Document'];
        };
      };
    };
  };
  api_v1_documents_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Document'];
        };
      };
    };
  };
  api_v1_documents_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_v1_documents_attach_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['DocumentAttachmentRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['DocumentAttachmentRequest'];
        'multipart/form-data': ApiComponents['schemas']['DocumentAttachmentRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Document'];
        };
      };
    };
  };
  api_v1_documents_file_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          '*/*': Blob;
        };
      };
    };
  };
  api_v1_offerings_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedOfferingListList'];
        };
      };
    };
  };
  api_v1_offerings_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['OfferingWriteRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['OfferingWriteRequest'];
        'multipart/form-data': ApiComponents['schemas']['OfferingWriteRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OfferingDetail'];
        };
      };
    };
  };
  api_v1_offerings_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OfferingDetail'];
        };
      };
    };
  };
  api_v1_offerings_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['OfferingWriteRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['OfferingWriteRequest'];
        'multipart/form-data': ApiComponents['schemas']['OfferingWriteRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OfferingDetail'];
        };
      };
    };
  };
  api_v1_offerings_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_v1_offerings_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedOfferingWriteRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedOfferingWriteRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedOfferingWriteRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OfferingDetail'];
        };
      };
    };
  };
  api_v1_offerings_submit_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OfferingDetail'];
        };
      };
    };
  };
  api_v1_offerings_subscriptions_list: {
    parameters: {
      query?: {
        page?: number;
      };
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedIssuerSubscriptionList'];
        };
      };
    };
  };
  api_v1_offerings_withdraw_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['OfferingWithdrawRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['OfferingWithdrawRequest'];
        'multipart/form-data': ApiComponents['schemas']['OfferingWithdrawRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OfferingDetail'];
        };
      };
    };
  };
  api_v1_subscriptions_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedSubscriptionListList'];
        };
      };
    };
  };
  api_v1_subscriptions_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['SubscriptionCreateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['SubscriptionCreateRequest'];
        'multipart/form-data': ApiComponents['schemas']['SubscriptionCreateRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SubscriptionDetail'];
        };
      };
    };
  };
  api_v1_subscriptions_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SubscriptionDetail'];
        };
      };
    };
  };
  api_v1_subscriptions_submit_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SubscriptionDetail'];
        };
      };
    };
  };
  api_v1_subscriptions_withdraw_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['SubscriptionWithdrawRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['SubscriptionWithdrawRequest'];
        'multipart/form-data': ApiComponents['schemas']['SubscriptionWithdrawRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SubscriptionDetail'];
        };
      };
    };
  };
  api_v1_tokens_list: {
    parameters: {
      query?: {
        company_uuid?: string;
        contract_address?: string;
        ordering?: string;
        page?: number;
        search?: string;
        status?: string;
        token_type?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedShareTokenListList'];
        };
      };
    };
  };
  api_v1_tokens_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['ShareTokenCreateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['ShareTokenCreateRequest'];
        'multipart/form-data': ApiComponents['schemas']['ShareTokenCreateRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ShareTokenDetail'];
        };
      };
    };
  };
  api_v1_tokens_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ShareTokenDetail'];
        };
      };
    };
  };
  api_v1_tokens_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ShareTokenDetail'];
        };
      };
    };
  };
  api_v1_tokens_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_v1_tokens_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ShareTokenDetail'];
        };
      };
    };
  };
  api_v1_tokens_deploy_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['TokenDeploymentStarted'];
        };
      };
    };
  };
  api_v1_tokens_holders_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ShareRegister'];
        };
      };
    };
  };
  api_v1_tokens_issuances_list: {
    parameters: {
      query?: {
        page?: number;
        status?: string;
      };
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedShareIssuanceListList'];
        };
      };
    };
  };
  api_v1_tokens_issue_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['ShareIssuanceCreateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['ShareIssuanceCreateRequest'];
        'multipart/form-data': ApiComponents['schemas']['ShareIssuanceCreateRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ShareIssuanceRequested'];
        };
      };
    };
  };
  api_v1_tokens_pause_submissions_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        submission_id: string;
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PauseSubmissionResponse'];
        };
      };
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PauseSubmissionResponse'];
        };
      };
    };
  };
  api_v1_tokens_pause_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['PauseSubmissionRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PauseSubmissionRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['PauseSubmissionRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PauseSubmissionResponse'];
        };
      };
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PauseSubmissionResponse'];
        };
      };
    };
  };
  api_v1_tokens_register_export_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'text/csv': string;
        };
      };
    };
  };
  api_v1_tokens_unpause_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['PauseSubmissionRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PauseSubmissionRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['PauseSubmissionRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PauseSubmissionResponse'];
        };
      };
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PauseSubmissionResponse'];
        };
      };
    };
  };
  api_v1_tokens_capital_increases_list: {
    parameters: {
      query?: {
        company?: string;
        ordering?: string;
        page?: number;
        search?: string;
        status?: string;
        token?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedCapitalIncreaseListList'];
        };
      };
    };
  };
  api_v1_tokens_capital_increases_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['CapitalIncreaseCreateRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['CapitalIncreaseCreateRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['CapitalIncreaseCreateRequestRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CapitalIncreaseDetail'];
        };
      };
    };
  };
  api_v1_tokens_capital_increases_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CapitalIncreaseDetail'];
        };
      };
    };
  };
  api_v1_tokens_capital_increases_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['CapitalIncreaseUpdateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['CapitalIncreaseUpdateRequest'];
        'multipart/form-data': ApiComponents['schemas']['CapitalIncreaseUpdateRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CapitalIncreaseUpdate'];
        };
      };
    };
  };
  api_v1_tokens_capital_increases_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_v1_tokens_capital_increases_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedCapitalIncreaseUpdateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedCapitalIncreaseUpdateRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedCapitalIncreaseUpdateRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CapitalIncreaseUpdate'];
        };
      };
    };
  };
  api_v1_tokens_capital_increases_submit_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['CapitalIncreaseSubmitted'];
        };
      };
    };
  };
  api_v1_tokens_issuance_requests_list: {
    parameters: {
      query?: {
        company?: string;
        ordering?: string;
        page?: number;
        status?: string;
        token?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedShareIssuanceRequestList'];
        };
      };
    };
  };
  api_v1_tokens_issuance_requests_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ShareIssuanceRequest'];
        };
      };
    };
  };
  trading_events_stream_retrieve: {
    parameters: {
      query?: {
        token?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'text/event-stream': string;
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'text/plain': string;
        };
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'text/plain': string;
        };
      };
    };
  };
  api_v1_trading_orders_list: {
    parameters: {
      query?: {
        order_type?: string;
        ordering?: string;
        page?: number;
        payment_asset?: string;
        search?: string;
        status?: string;
        token?: string;
        wallet_address?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedTransferOrderListList'];
        };
      };
    };
  };
  api_v1_trading_orders_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['TransferOrderDetail'];
        };
      };
    };
  };
  api_v1_trading_orders_action_context_retrieve: {
    parameters: {
      query: {
        owner_account_uuid: string;
      };
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderActionContext'];
        };
      };
    };
  };
  api_v1_trading_orders_cancel_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['OrderActionExecuteRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['OrderActionExecuteRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['OrderActionExecuteRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderActionSubmission'];
        };
      };
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderActionSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderActionSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
    };
  };
  api_v1_trading_orders_cancel_message_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
    };
  };
  api_v1_trading_orders_cancel_message_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['OrderActionIdentityRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['OrderActionIdentityRequest'];
        'multipart/form-data': ApiComponents['schemas']['OrderActionIdentityRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderActionSubmission'];
        };
      };
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderActionSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderActionSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
    };
  };
  api_v1_trading_orders_modifications_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['TransferOrderList'];
        };
      };
    };
  };
  api_v1_trading_orders_modify_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['OrderActionExecuteRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['OrderActionExecuteRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['OrderActionExecuteRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderActionSubmission'];
        };
      };
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderActionSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderActionSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
    };
  };
  api_v1_trading_orders_modify_message_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['OrderActionModifyRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['OrderActionModifyRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['OrderActionModifyRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderActionSubmission'];
        };
      };
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderActionSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderActionSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
    };
  };
  api_v1_trading_orders_swap_retrieve: {
    parameters: {
      query: {
        owner_account_uuid: string;
        settlement_digest?: string;
        swap_uuid: string;
        wallet_uuid: string;
      };
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SettlementSwapOrderForSigning'];
        };
      };
    };
  };
  api_v1_trading_orders_swap_approval_broadcast_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['SettlementApprovalBroadcastRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['SettlementApprovalBroadcastRequest'];
        'multipart/form-data': ApiComponents['schemas']['SettlementApprovalBroadcastRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SettlementApprovalReceipt'];
        };
      };
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SettlementApprovalUncertain'];
        };
      };
    };
  };
  api_v1_trading_orders_swap_approval_data_retrieve: {
    parameters: {
      query: {
        owner_account_uuid: string;
        settlement_digest: string;
        swap_uuid: string;
        wallet_uuid: string;
      };
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ApprovalDataResponse'];
        };
      };
    };
  };
  api_v1_trading_orders_swap_approval_status_retrieve: {
    parameters: {
      query: {
        owner_account_uuid: string;
        settlement_digest: string;
        swap_uuid: string;
        wallet_uuid: string;
      };
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SettlementApprovalStatus'];
        };
      };
    };
  };
  api_v1_trading_orders_swap_sign_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['SettlementSignatureRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['SettlementSignatureRequest'];
        'multipart/form-data': ApiComponents['schemas']['SettlementSignatureRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['SettlementSwapOrder'];
        };
      };
    };
  };
  api_v1_trading_orders_actions_retrieve: {
    parameters: {
      query: {
        owner_account_uuid: string;
      };
      header?: never;
      path: {
        action_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderActionSubmission'];
        };
      };
    };
  };
  api_v1_trading_orders_create_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['SignedOrderSubmissionRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['SignedOrderSubmissionRequest'];
        'multipart/form-data': ApiComponents['schemas']['SignedOrderSubmissionRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderSubmission'];
        };
      };
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderSubmission'];
        };
      };
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json':
            | ApiComponents['schemas']['OrderSubmission']
            | {
                [key: string]: unknown;
              };
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
    };
  };
  api_v1_trading_orders_create_message_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['TransferOrderCreateRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['TransferOrderCreateRequest'];
        'multipart/form-data': ApiComponents['schemas']['TransferOrderCreateRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderSubmission'];
        };
      };
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
    };
  };
  api_v1_trading_orders_submissions_retrieve: {
    parameters: {
      query: {
        owner_account_uuid: string;
      };
      header?: never;
      path: {
        submission_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderSubmission'];
        };
      };
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            [key: string]: unknown;
          };
        };
      };
    };
  };
  api_v1_trading_swaps_list: {
    parameters: {
      query: {
        ordering?: string;
        page?: number;
        wallet_address: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedSwapOrderListList'];
        };
      };
    };
  };
  api_v1_trading_tokens_list: {
    parameters: {
      query?: {
        ordering?: string;
        page?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedShareTokenListList'];
        };
      };
    };
  };
  api_v1_trading_tokens_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['ShareTokenList'];
        };
      };
    };
  };
  api_v1_trading_tokens_market_data_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['MarketData'];
        };
      };
    };
  };
  api_v1_trading_tokens_order_book_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['OrderBook'];
        };
      };
    };
  };
  api_v1_trading_transfers_broadcast_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['TradingBroadcastTransferRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['TradingBroadcastTransferRequest'];
        'multipart/form-data': ApiComponents['schemas']['TradingBroadcastTransferRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['TokenTransferReceipt'];
        };
      };
    };
  };
  api_v1_trading_transfers_prepare_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['PrepareTransferRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PrepareTransferRequest'];
        'multipart/form-data': ApiComponents['schemas']['PrepareTransferRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PreparedTokenTransfer'];
        };
      };
    };
  };
  api_v1_trading_wallets_balances_retrieve: {
    parameters: {
      query: {
        wallet_address: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['TradingWalletBalances'];
        };
      };
    };
  };
  api_v1_trading_whitelist_status_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        address: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistStatus'];
        };
      };
    };
  };
  api_v1_whitelist_list: {
    parameters: {
      query?: {
        date_from?: string;
        date_to?: string;
        is_whitelisted?: boolean;
        ordering?: string;
        page?: number;
        status?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedWhitelistEntryList'];
        };
      };
    };
  };
  api_v1_whitelist_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistEntry'];
        };
      };
    };
  };
  api_v1_whitelist_add_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['WhitelistAddRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['WhitelistAddRequest'];
        'multipart/form-data': ApiComponents['schemas']['WhitelistAddRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistChange'];
        };
      };
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistChange'];
        };
      };
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistChange'];
        };
      };
    };
  };
  api_v1_whitelist_batch_add_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['WhitelistBatchAddRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['WhitelistBatchAddRequest'];
        'multipart/form-data': ApiComponents['schemas']['WhitelistBatchAddRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistBatchResponse'];
        };
      };
    };
  };
  api_v1_whitelist_entry_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        address: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistEntry'];
        };
      };
    };
  };
  api_v1_whitelist_export_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'text/csv': string;
        };
      };
    };
  };
  api_v1_whitelist_remove_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['WhitelistRemoveRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['WhitelistRemoveRequest'];
        'multipart/form-data': ApiComponents['schemas']['WhitelistRemoveRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistChange'];
        };
      };
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistChange'];
        };
      };
    };
  };
  api_v1_whitelist_sync_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        address: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WhitelistSyncResponse'];
        };
      };
    };
  };
  api_wallets_list: {
    parameters: {
      query?: {
        address?: string;
        chain?: string;
        ordering?: string;
        page?: number;
        verification_status?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PaginatedWalletList'];
        };
      };
    };
  };
  api_wallets_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['WalletRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['WalletRequest'];
        'multipart/form-data': ApiComponents['schemas']['WalletRequest'];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Wallet'];
        };
      };
    };
  };
  api_wallets_retrieve: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Wallet'];
        };
      };
    };
  };
  api_wallets_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['WalletRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['WalletRequest'];
        'multipart/form-data': ApiComponents['schemas']['WalletRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Wallet'];
        };
      };
    };
  };
  api_wallets_destroy: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
    };
  };
  api_wallets_partial_update: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': ApiComponents['schemas']['PatchedWalletRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PatchedWalletRequest'];
        'multipart/form-data': ApiComponents['schemas']['PatchedWalletRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Wallet'];
        };
      };
    };
  };
  api_wallets_broadcast_transfer_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['BroadcastTransferRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['BroadcastTransferRequest'];
        'multipart/form-data': ApiComponents['schemas']['BroadcastTransferRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['BroadcastTransferResponse'];
        };
      };
    };
  };
  api_wallets_holdings_list: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['Holding'][];
        };
      };
    };
  };
  api_wallets_prepare_transfer_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['PrepareWalletTransferRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['PrepareWalletTransferRequest'];
        'multipart/form-data': ApiComponents['schemas']['PrepareWalletTransferRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['PreparedWalletTransfer'];
        };
      };
    };
  };
  api_wallets_request_verification_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WalletVerificationChallenge'];
        };
      };
    };
  };
  api_wallets_sync_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WalletSyncResponse'];
        };
      };
    };
  };
  api_wallets_verify_signature_create: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        uuid: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['WalletVerificationSignatureRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['WalletVerificationSignatureRequest'];
        'multipart/form-data': ApiComponents['schemas']['WalletVerificationSignatureRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['WalletVerificationResult'];
        };
      };
    };
  };
  api_wallets_batch_check_balances_create: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': ApiComponents['schemas']['BatchBalanceRequestRequest'];
        'application/x-www-form-urlencoded': ApiComponents['schemas']['BatchBalanceRequestRequest'];
        'multipart/form-data': ApiComponents['schemas']['BatchBalanceRequestRequest'];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': ApiComponents['schemas']['BatchBalanceResponse'];
        };
      };
    };
  };
}
export type TradingEventType =
  | 'order_cancelled'
  | 'order_created'
  | 'order_matched'
  | 'order_modified'
  | 'swap_completed'
  | 'swap_expired'
  | 'swap_failed'
  | 'swap_signed';
