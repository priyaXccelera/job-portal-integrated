import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminDashboard } from './AdminDashboard';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <AdminDashboard />
    </MemoryRouter>
  );
});
