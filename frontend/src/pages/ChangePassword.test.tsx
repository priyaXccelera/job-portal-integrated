import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ChangePassword } from './ChangePassword';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <ChangePassword />
    </MemoryRouter>
  );
});
