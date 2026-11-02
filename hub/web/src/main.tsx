import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ApiError } from './api/client';
import { App } from './App';
import { LogsProvider } from './app/logs';
import { applyScheme } from './theme/mode';
import { FeedbackProvider } from './ui/feedback';
import './theme/global.css';

applyScheme();

// Every screen keeps itself current: data refreshes in the background every 15 s and when the tab comes back.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 15_000,
      staleTime: 5_000,
      retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
    },
  },
});

const root = document.getElementById('root');
if (!root) throw new Error('index.html has no #root');

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <FeedbackProvider>
          <LogsProvider>
            <App />
          </LogsProvider>
        </FeedbackProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
