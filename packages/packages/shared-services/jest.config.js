export default {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src'],
  testMatch: ['**/__tests__/**/*.ts', '**/?(*.)+(spec|test).ts'],
  collectCoverageFrom: ['src/**/*.ts', '!src/**/*.d.ts', '!src/**/index.ts'],
  moduleNameMapper: {
    '^@ledova/shared-constants$': '<rootDir>/../shared-constants/src/index.ts',
    '^@ledova/shared-types$': '<rootDir>/../shared-types/src/index.ts',
    '^@ledova/shared-utils$': '<rootDir>/../shared-utils/src/index.ts',
  },
};
