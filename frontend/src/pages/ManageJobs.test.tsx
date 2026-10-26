import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ManageJobs } from './ManageJobs';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <ManageJobs />
    </MemoryRouter>
  );
});
