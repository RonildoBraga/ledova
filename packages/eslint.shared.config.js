import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import prettierPlugin from 'eslint-plugin-prettier';
import prettierConfig from 'eslint-config-prettier';
import importPlugin from 'eslint-plugin-import';

export default tseslint.config(
  { ignores: ['dist', 'node_modules'] },
  {
    extends: [js.configs.recommended, prettierConfig, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'module',
      parserOptions: {
        project: './tsconfig.json',
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      prettier: prettierPlugin,
      import: importPlugin,
    },
    settings: {
      'import/resolver': {
        typescript: {
          alwaysTryTypes: true,
        },
      },
    },
    rules: {
      'prettier/prettier': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/explicit-function-return-type': 'off',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-explicit-any': 'error',

      // Naming conventions
      // Allow both camelCase and snake_case for interface/type properties (REST API URL params convention)
      '@typescript-eslint/naming-convention': [
        'error',
        {
          selector: 'default',
          format: ['camelCase'],
          leadingUnderscore: 'allow',
          trailingUnderscore: 'allow',
        },
        {
          selector: 'import',
          format: ['camelCase', 'PascalCase'],
        },
        {
          selector: 'variable',
          format: ['camelCase', 'UPPER_CASE', 'PascalCase'],
        },
        {
          selector: 'typeLike',
          format: ['PascalCase'],
        },
        {
          selector: ['objectLiteralProperty', 'typeProperty'],
          format: null,
        },
      ],

      // Import rules for dependency management
      'import/no-cycle': 'error', // Prevent circular dependencies
      'import/order': [
        'error',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          'newlines-between': 'always',
          alphabetize: { order: 'asc', caseInsensitive: true },
        },
      ],
      'import/no-restricted-paths': [
        'error',
        {
          zones: [
            // Constants cannot import from any other package
            {
              target: './packages/shared-constants/src',
              from: './packages/shared-types',
              message: 'Constants cannot import from Types',
            },
            {
              target: './packages/shared-constants/src',
              from: './packages/shared-utils',
              message: 'Constants cannot import from Utils',
            },
            {
              target: './packages/shared-constants/src',
              from: './packages/shared-services',
              message: 'Constants cannot import from Services',
            },
            // Types cannot import from Utils or Services
            {
              target: './packages/shared-types/src',
              from: './packages/shared-utils',
              message: 'Types cannot import from Utils',
            },
            {
              target: './packages/shared-types/src',
              from: './packages/shared-services',
              message: 'Types cannot import from Services',
            },
            // Utils cannot import from Services
            {
              target: './packages/shared-utils/src',
              from: './packages/shared-services',
              message: 'Utils cannot import from Services',
            },
          ],
        },
      ],
    },
  },
);
