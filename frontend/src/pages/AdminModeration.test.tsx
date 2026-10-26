import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminModeration } from './AdminModeration';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <AdminModeration />
    </MemoryRouter>
  );
});
