# Query Parameters Standards

This document outlines the standards for defining query parameter interfaces across the Ledova shared packages and consuming applications.

## Table of Contents

- [Overview](#overview)
- [Core Principles](#core-principles)
- [Composable Interfaces](#composable-interfaces)
- [Composed Base Types](#composed-base-types)
- [Implementation Guide](#implementation-guide)
- [Decision Matrix](#decision-matrix)
- [Examples](#examples)
- [Consistency Enforcement](#consistency-enforcement)

## Overview

Query parameter interfaces define the shape of URL query parameters for API endpoints. We use a **composition-based approach** following the Interface Segregation Principle (ISP) to create flexible, reusable, and maintainable type definitions.

### Naming Convention

All query parameters use **snake_case** following REST API URL standards:

```typescript
// Correct
interface MyQueryParams {
  page_size?: number;
  start_date?: string;
  user_account?: string;
}

// Incorrect - don't use camelCase for query params
interface MyQueryParams {
  pageSize?: number; // Wrong
  startDate?: string; // Wrong
  userAccount?: string; // Wrong
}
```

## Core Principles

### 1. Interface Segregation Principle (ISP)

Small, focused interfaces that can be composed as needed. Each interface has a single responsibility.

### 2. Composition Over Inheritance

Use TypeScript intersection types (`&`) and `extends` to combine interfaces rather than creating deep inheritance hierarchies.

### 3. Single Responsibility Principle (SRP)

Each composable interface handles one concern (pagination, ordering, date filtering, etc.).

### 4. Don't Repeat Yourself (DRY)

Common patterns are defined once in composable interfaces and reused across domain-specific types.

## Composable Interfaces

These are the building blocks defined in `@ledova/shared-types/api`:

### PaginationParams

For page-based pagination (list endpoints):

```typescript
export interface PaginationParams {
  page?: number;
  page_size?: number;
}
```

**Use when:** Endpoint returns a paginated list with `next`/`previous` links.

### LimitParams

For limit-based pagination (time-series, snapshots):

```typescript
export interface LimitParams {
  limit?: number;
  offset?: number;
}
```

**Use when:** Endpoint returns time-series data or needs offset-based access.

### OrderingParams

For sortable endpoints:

```typescript
export interface OrderingParams {
  order_by?: string;
}
```

**Use when:** Endpoint supports sorting by field name (e.g., `order_by=created_at` or `order_by=-created_at`).

### DateRangeParams

For date-filtered endpoints:

```typescript
export interface DateRangeParams {
  start_date?: string;
  end_date?: string;
}
```

**Use when:** Endpoint filters results by date range.

### SearchParams

For searchable endpoints:

```typescript
export interface SearchParams {
  search?: string;
}
```

**Use when:** Endpoint supports text search across fields.

## Composed Base Types

These pre-composed types cover the most common endpoint patterns:

### BaseQueryParams

For standard paginated list endpoints:

```typescript
export type BaseQueryParams = PaginationParams & OrderingParams;
// Provides: page, page_size, order_by
```

**Use when:** Standard CRUD list endpoint with pagination and sorting.

### TimeSeriesQueryParams

For time-series data and snapshot endpoints:

```typescript
export type TimeSeriesQueryParams = LimitParams & OrderingParams & DateRangeParams;
// Provides: limit, offset, order_by, start_date, end_date
```

**Use when:** Endpoint returns historical/time-series data with date filtering.

## Implementation Guide

### Step 1: Identify Endpoint Type

Determine what type of data your endpoint returns:

| Endpoint Type  | Characteristics                                | Base Type               |
| -------------- | ---------------------------------------------- | ----------------------- |
| Paginated List | Returns `count`, `next`, `previous`, `results` | `BaseQueryParams`       |
| Time Series    | Historical data with date range                | `TimeSeriesQueryParams` |
| Small List     | Few items, no pagination needed                | `OrderingParams`        |
| Single Item    | Detail endpoint, no params needed              | None (custom only)      |

### Step 2: Extend Appropriate Base Type

```typescript
import type { BaseQueryParams, TimeSeriesQueryParams, OrderingParams } from '../api';

// For paginated list
export interface AssetQueryParams extends BaseQueryParams {
  symbol?: string;
  asset_type?: AssetType;
  search?: string;
}

// For time-series data
export interface AssetSnapshotQueryParams extends TimeSeriesQueryParams {
  asset?: string;
  min_price?: number;
  max_price?: number;
}

// For small lists (no pagination)
export interface WidgetQueryParams extends OrderingParams {
  user_account?: string;
  name?: WidgetNameType;
}
```

### Step 3: Add Domain-Specific Parameters

Add only the parameters specific to your domain entity. The base types already provide common functionality.

### Step 4: Document with JSDoc

Include comments explaining the interface and its use of base types:

```typescript
/**
 * Query parameters for asset endpoints.
 * Extends BaseQueryParams for page-based pagination.
 *
 * NAMING CONVENTION: Query params use snake_case following REST API URL standards.
 */
export interface AssetQueryParams extends BaseQueryParams {
  // domain-specific params
}
```

## Decision Matrix

Use this matrix to determine which base type to extend:

| Question                                | Yes →                                 | No →             |
| --------------------------------------- | ------------------------------------- | ---------------- |
| Does endpoint return paginated results? | Use `BaseQueryParams`                 | Continue         |
| Is it time-series/historical data?      | Use `TimeSeriesQueryParams`           | Continue         |
| Does endpoint support sorting?          | Use `OrderingParams`                  | Custom interface |
| Need date filtering on paginated list?  | `BaseQueryParams` + `DateRangeParams` | -                |

### Composition Examples

```typescript
// Paginated list with date filtering
export interface TransactionQueryParams extends BaseQueryParams, DateRangeParams {
  wallet?: string;
  chain?: string;
}

// Time-series with search (rare but possible)
export interface LogQueryParams extends TimeSeriesQueryParams, SearchParams {
  level?: 'INFO' | 'WARN' | 'ERROR';
}

// Simple sorted list
export interface WidgetQueryParams extends OrderingParams {
  user_account?: string;
}
```

## Examples

### Example 1: Asset List Endpoint

```typescript
// Asset is a paginated list with search
export interface AssetQueryParams extends BaseQueryParams {
  uuid?: string;
  symbol?: string;
  name?: string;
  asset_type?: AssetType;
  is_active?: boolean;
  search?: string; // Added directly since it's domain-specific
}
```

### Example 2: Asset Price Snapshots

```typescript
// Snapshots are time-series data
export interface AssetSnapshotQueryParams extends TimeSeriesQueryParams {
  asset?: string;
  source_start_date?: string;
  source_end_date?: string;
  min_price?: number;
  max_price?: number;
}
```

### Example 3: Transactions

```typescript
// Transactions are paginated with date filtering
export interface TransactionQueryParams extends BaseQueryParams, DateRangeParams {
  wallet?: string;
  chain?: string;
  transaction_type?: TransactionType;
  asset?: string;
}
```

### Example 4: Portfolio Snapshots

```typescript
// Portfolio snapshots are time-series
export interface PortfolioSnapshotQueryParams extends TimeSeriesQueryParams {
  portfolio?: string;
  user_account?: string;
  user_profile?: string;
  snapshot_reason?: PortfolioSnapshotReason;
}
```

### Example 5: User Preferences (No Pagination)

```typescript
// Single record per user, just sorting
export interface UserPreferencesQueryParams extends OrderingParams {
  userProfile?: string;
  withFavoriteAccount?: boolean;
  withFavoritePortfolio?: boolean;
}
```

## Consistency Enforcement

### Code Review Checklist

When reviewing PRs that add new query parameter interfaces:

1. **Does it extend the appropriate base type?**
   - Paginated endpoints → `BaseQueryParams`
   - Time-series endpoints → `TimeSeriesQueryParams`
   - Small lists → `OrderingParams`

2. **Are parameters named with snake_case?**
   - `user_account` not `userAccount`
   - `page_size` not `pageSize`

3. **Is the JSDoc comment present?**
   - Documents what base type is used
   - Mentions naming convention

4. **Are common params delegated to base types?**
   - Don't add `page`, `page_size` manually if extending `BaseQueryParams`
   - Don't add `limit`, `offset`, `start_date`, `end_date` if extending `TimeSeriesQueryParams`

### ESLint Rules (Recommended)

Consider adding custom ESLint rules to enforce:

```javascript
// Example rule concept (not actual implementation)
{
  "rules": {
    "no-duplicate-pagination-params": "error",
    "require-query-params-jsdoc": "warn",
    "snake-case-query-params": "error"
  }
}
```

### TypeScript Compiler Checks

TypeScript will catch many issues automatically:

- Missing required parameters
- Type mismatches
- Unused parameters (with `noUnusedParameters`)

### Pre-Commit Validation

Run type checking before commits:

```bash
npm run typecheck
```

## Migration Guide

When updating existing interfaces to follow these standards:

### Before

```typescript
export interface OldTransactionQueryParams {
  page?: number;
  page_size?: number;
  order_by?: string;
  start_date?: string;
  end_date?: string;
  wallet?: string;
}
```

### After

```typescript
import type { BaseQueryParams, DateRangeParams } from '../api';

/**
 * Query parameters for transaction endpoints.
 * Extends BaseQueryParams for page-based pagination.
 *
 * NAMING CONVENTION: Query params use snake_case following REST API URL standards.
 */
export interface TransactionQueryParams extends BaseQueryParams, DateRangeParams {
  wallet?: string;
}
```

### Migration Steps

1. Identify which base type(s) apply
2. Import from `../api`
3. Replace duplicated params with `extends`
4. Add JSDoc documentation
5. Test that types still work correctly

## Summary

| Interface               | Params Included                                         | Use For                  |
| ----------------------- | ------------------------------------------------------- | ------------------------ |
| `PaginationParams`      | `page`, `page_size`                                     | Page-based pagination    |
| `LimitParams`           | `limit`, `offset`                                       | Limit-based pagination   |
| `OrderingParams`        | `order_by`                                              | Sorting                  |
| `DateRangeParams`       | `start_date`, `end_date`                                | Date filtering           |
| `SearchParams`          | `search`                                                | Text search              |
| `BaseQueryParams`       | `page`, `page_size`, `order_by`                         | Standard paginated lists |
| `TimeSeriesQueryParams` | `limit`, `offset`, `order_by`, `start_date`, `end_date` | Time-series/snapshots    |

Following these standards ensures consistency across the codebase, reduces duplication, and makes the API contracts clearer for all developers.
