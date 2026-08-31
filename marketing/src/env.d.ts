/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_LEDOVA_URL: string;
  readonly VITE_HOST: string;
  readonly VITE_PORT: string;
  readonly VITE_ALLOWED_HOSTS: string;
  readonly NEXT_PUBLIC_GOOGLE_MAPS_API_KEY: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
