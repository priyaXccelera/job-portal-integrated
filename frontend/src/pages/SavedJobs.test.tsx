import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SavedJobs } from './SavedJobs';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <SavedJobs />
    </MemoryRouter>
  );
});
