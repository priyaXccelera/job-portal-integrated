import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { JobDetail } from './JobDetail';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <JobDetail />
    </MemoryRouter>
  );
});
