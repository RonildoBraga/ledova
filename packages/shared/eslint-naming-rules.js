export const namingConventionRules = {
  '@typescript-eslint/naming-convention': [
    'error',
    {
      selector: 'interface',
      format: ['PascalCase'],
      custom: {
        regex: '^[A-Z][a-zA-Z0-9]*$',
        match: true,
      },
    },
    {
      selector: 'typeAlias',
      format: ['PascalCase'],
      custom: {
        regex: '^[A-Z][a-zA-Z0-9]*$',
        match: true,
      },
    },
    {
      selector: 'property',
      format: ['camelCase'],
      leadingUnderscore: 'allow',
      filter: {
        regex:
          '^(page|page_size|order_by|start_date|end_date|min_.*|max_.*|search_query|is_.*|has_.*|.*_uuid|.*_id|.*_at|.*_type|.*_status|.*_currency|.*_network|.*_reason|.*_profile|source_.*|account_type|transaction_type|bank_name|cash_account|asset_holding|document_type|short_name|country_code|exchange_short_name|settlement_.*_date|settlement_permission|contract_address|underlying_ticker|user_account|flow_type|snapshot_reason|verification_status|include_periods|include_benchmarks|reference_date)$',
        match: false,
      },
    },
    {
      selector: 'enumMember',
      format: ['UPPER_CASE', 'PascalCase'],
    },
  ],
};

export const restrictedTypeSyntaxRules = {
  'no-restricted-syntax': [
    'error',
    {
      selector:
        'TSInterfaceDeclaration[id.name=/^(?!Signin|Signup|EmailVerification|TokenRefresh|GenerateDocument).*Payload$/]',
      message:
        'Avoid creating *Payload interfaces for entities. Use TypeScript utility types instead (e.g., Omit<Entity, "uuid">). See Resource Types Philosophy.',
    },
    {
      selector: 'TSInterfaceDeclaration[id.name=/^(Create|Update)[A-Z].*(?<!Request)(?<!Response)$/]',
      message:
        'Use TypeScript utility types (e.g., type CreateEntity = Omit<Entity, "uuid">) instead of interfaces for entity variations. API request and response shapes, named *Request or *Response, are exempt.',
    },
    {
      selector:
        'TSInterfaceDeclaration[id.name=/.*(?:QueryParams|Filters)$/] TSPropertySignature[key.name=/^(minValue|maxValue|startDate|endDate|searchQuery|orderBy|pageSize)$/]',
      message:
        'Query parameter fields in QueryParams/Filters interfaces should use snake_case. Use min_value, max_value, start_date, end_date, search_query, order_by, page_size instead.',
    },
  ],
};

export const namingConventions = {
  rules: {
    ...namingConventionRules,
    ...restrictedTypeSyntaxRules,
  },
};

export default namingConventions;
