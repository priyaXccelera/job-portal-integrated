import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminAnalytics } from './AdminAnalytics';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <AdminAnalytics />
    </MemoryRouter>
  );
});
