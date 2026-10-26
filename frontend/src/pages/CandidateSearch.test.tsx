import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CandidateSearch } from './CandidateSearch';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <CandidateSearch />
    </MemoryRouter>
  );
});
