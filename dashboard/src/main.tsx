import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiClientProvider } from '@ledova/shared';
import apiClient from '@services/apiClient';
import './styles/index.css';

const queryClient = new QueryClient();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider client={apiClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ApiClientProvider>
    </QueryClientProvider>
  </StrictMode>,
);
