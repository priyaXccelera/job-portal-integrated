import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { JobSearch } from './JobSearch';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <JobSearch />
    </MemoryRouter>
  );
});
