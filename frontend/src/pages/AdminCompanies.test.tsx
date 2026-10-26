import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminCompanies } from './AdminCompanies';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <AdminCompanies />
    </MemoryRouter>
  );
});
