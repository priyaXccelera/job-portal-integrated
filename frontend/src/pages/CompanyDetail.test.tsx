import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CompanyDetail } from './CompanyDetail';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <CompanyDetail />
    </MemoryRouter>
  );
});
