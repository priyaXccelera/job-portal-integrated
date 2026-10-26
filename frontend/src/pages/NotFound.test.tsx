import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NotFound } from './NotFound';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <NotFound />
    </MemoryRouter>
  );
});
