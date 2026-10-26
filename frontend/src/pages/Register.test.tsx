import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Register } from './Register';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>
  );
});
