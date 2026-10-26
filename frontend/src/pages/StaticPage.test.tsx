import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StaticPage } from './StaticPage';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <StaticPage />
    </MemoryRouter>
  );
});
