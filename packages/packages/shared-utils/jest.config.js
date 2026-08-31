export default {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src', '<rootDir>/tests'],
  testMatch: ['**/__tests__/**/*.ts', '**/?(*.)+(spec|test).ts'],
  collectCoverageFrom: ['src/**/*.ts', '!src/**/*.d.ts', '!src/**/index.ts'],
  moduleNameMapper: {
    '^@ledova/shared-constants$': '<rootDir>/../shared-constants/src',
    '^@ledova/shared-types$': '<rootDir>/../shared-types/src',
  },
};
