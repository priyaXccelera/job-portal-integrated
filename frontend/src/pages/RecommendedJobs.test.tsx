import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RecommendedJobs } from './RecommendedJobs';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <RecommendedJobs />
    </MemoryRouter>
  );
});
