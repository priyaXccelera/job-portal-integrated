import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NotificationPreferences } from './NotificationPreferences';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <NotificationPreferences />
    </MemoryRouter>
  );
});
