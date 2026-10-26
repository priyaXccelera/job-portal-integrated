import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NotAuthorized } from './NotAuthorized';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <NotAuthorized />
    </MemoryRouter>
  );
});
