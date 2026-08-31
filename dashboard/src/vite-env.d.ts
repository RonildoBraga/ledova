/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_HOST: string;
  readonly VITE_PORT: string;
  readonly VITE_ALLOWED_HOSTS: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
