import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NotificationsPage } from './NotificationsPage';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <NotificationsPage />
    </MemoryRouter>
  );
});
