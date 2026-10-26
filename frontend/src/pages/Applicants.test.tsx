import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Applicants } from './Applicants';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <Applicants />
    </MemoryRouter>
  );
});
