import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Home } from './Home';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <Home />
    </MemoryRouter>
  );
});
