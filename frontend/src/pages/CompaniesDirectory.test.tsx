import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CompaniesDirectory } from './CompaniesDirectory';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <CompaniesDirectory />
    </MemoryRouter>
  );
});
