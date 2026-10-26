import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CompanyProfileEditor } from './CompanyProfileEditor';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <CompanyProfileEditor />
    </MemoryRouter>
  );
});
