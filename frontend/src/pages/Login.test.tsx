import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Login } from './Login';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  );
});
