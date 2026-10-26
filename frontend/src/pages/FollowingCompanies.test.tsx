import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { FollowingCompanies } from './FollowingCompanies';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <FollowingCompanies />
    </MemoryRouter>
  );
});
