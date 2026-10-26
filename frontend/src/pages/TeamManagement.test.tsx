import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TeamManagement } from './TeamManagement';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <TeamManagement />
    </MemoryRouter>
  );
});
