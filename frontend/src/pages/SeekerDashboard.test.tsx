import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SeekerDashboard } from './SeekerDashboard';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <SeekerDashboard />
    </MemoryRouter>
  );
});
