import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { JobAlerts } from './JobAlerts';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <JobAlerts />
    </MemoryRouter>
  );
});
