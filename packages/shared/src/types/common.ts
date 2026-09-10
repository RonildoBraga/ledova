export interface BaseEntity {
  uuid: string;
  createdAt: string;
  updatedAt: string;
}

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
