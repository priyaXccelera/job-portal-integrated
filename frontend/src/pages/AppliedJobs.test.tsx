import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppliedJobs } from './AppliedJobs';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <AppliedJobs />
    </MemoryRouter>
  );
});
