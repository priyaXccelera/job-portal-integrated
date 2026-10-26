import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RecruiterDashboard } from './RecruiterDashboard';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <RecruiterDashboard />
    </MemoryRouter>
  );
});
