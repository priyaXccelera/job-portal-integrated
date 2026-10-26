import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminUsers } from './AdminUsers';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <AdminUsers />
    </MemoryRouter>
  );
});
