import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminMasterData } from './AdminMasterData';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <AdminMasterData />
    </MemoryRouter>
  );
});
